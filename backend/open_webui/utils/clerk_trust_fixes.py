"""
Boot-time fixes for the Ruimtemeesters Clerk-trust auth model.

OpenWebUI defaults new OIDC signups to role='pending' (admin-approval gate)
and persists that default in the `config` table on first boot via
PersistentConfig. For Ruimtemeesters, Clerk auth IS the auth — every
Clerk-verified user should land active, matching the trust model in
projectbeheer and the other RM apps.

Two fixes are applied on every lifespan startup, both gated on the operator
having opted out of the pending gate (env DEFAULT_USER_ROLE != 'pending'):

1. Force the env value over any stale persisted PersistentConfig, so
   `docker compose up` with a new env actually takes effect on existing
   deployments (where the first boot already cached 'pending' in the DB).

2. Migrate any users currently sitting at role='pending' to 'user', so
   colleagues who hit the gate before the fix landed don't stay
   stranded behind the pending overlay.

The bulk migration is hard-coded to promote pending → 'user' (never to
'admin') so that an operator misconfiguring DEFAULT_USER_ROLE=admin
cannot mass-escalate every pending user on the next restart. Admin
promotion remains a deliberate per-user action via the Admin Panel.
"""

import logging
import os

from open_webui.config import DEFAULT_USER_ROLE
from open_webui.internal.db import get_db
from open_webui.models.users import User

log = logging.getLogger(__name__)

# OpenWebUI's role enum (see routers/auths.py validation against this set).
_VALID_ROLES = {'pending', 'user', 'admin'}

# Target role for the pending → active migration. Hard-coded — even if the
# operator sets DEFAULT_USER_ROLE=admin, we never bulk-promote to admin.
_PENDING_MIGRATION_TARGET = 'user'


def apply_clerk_trust_fixes() -> None:
    env_role = os.environ.get('DEFAULT_USER_ROLE')
    if not env_role or env_role == 'pending':
        return
    if env_role not in _VALID_ROLES:
        log.warning('Ignoring invalid DEFAULT_USER_ROLE=%r (not in %s)', env_role, _VALID_ROLES)
        return

    if DEFAULT_USER_ROLE.value != env_role:
        log.info(
            'Overriding persisted DEFAULT_USER_ROLE=%r with env value %r',
            DEFAULT_USER_ROLE.value,
            env_role,
        )
        DEFAULT_USER_ROLE.value = env_role
        DEFAULT_USER_ROLE.save()

    try:
        with get_db() as db:
            updated = (
                db.query(User)
                .filter(User.role == 'pending')
                .update({User.role: _PENDING_MIGRATION_TARGET}, synchronize_session=False)
            )
            if updated:
                db.commit()
                log.info(
                    'Promoted %d pending user(s) to role=%r',
                    updated,
                    _PENDING_MIGRATION_TARGET,
                )
    except Exception as e:
        log.warning('Failed to migrate pending users: %s', e)
