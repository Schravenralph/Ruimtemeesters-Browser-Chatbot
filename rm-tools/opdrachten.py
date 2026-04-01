"""
title: Ruimtemeesters Opdrachten Scanner
description: Search and manage DAS/inhuur assignments from TenderNED and other platforms. View inbox, pipeline, and historical library.
author: Ruimtemeesters
version: 1.1.0
requirements: httpx
"""

import httpx
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        opdrachten_api_url: str = Field(default="http://opdrachten-api:6300", description="Base URL of the Opdrachten Scanner API")
        api_key: str = Field(default="", description="Service API key (X-API-Key header)")
        timeout: int = Field(default=30, description="Request timeout in seconds")

    def __init__(self):
        self.valves = self.Valves()

    def _auth_headers(self, __request__=None) -> dict:
        """Get auth headers: prefer Clerk token, fall back to API key."""
        if __request__ is not None:
            token = getattr(__request__, 'cookies', {}).get('oauth_id_token') or getattr(__request__, 'cookies', {}).get('__session')
            if token:
                return {"Authorization": f"Bearer {token}"}
        if self.valves.api_key:
            return {"X-API-Key": self.valves.api_key}
        return {}

    async def get_inbox(self, limit: int = 20, __user__: dict = {}, __request__=None) -> str:
        """
        Get new assignment opportunities waiting in the inbox (not yet triaged).
        :param limit: Maximum number of items to return (default 20, max 100)
        :return: Inbox items with assignment details, platform, buyer, and deadline
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.opdrachten_api_url}/api/inbox", params={"limit": min(limit, 100)}, headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def get_pipeline(self, __user__: dict = {}, __request__=None) -> str:
        """
        Get the current assignment pipeline — items organized by stage (interesse, offerte, gegund, actief, afgerond).
        :return: Pipeline items grouped by stage with details and deadlines
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.opdrachten_api_url}/api/pipeline", headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def get_pipeline_deadlines(self, __user__: dict = {}, __request__=None) -> str:
        """
        Get pipeline items with upcoming deadlines.
        :return: Items sorted by deadline date
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.opdrachten_api_url}/api/pipeline/deadlines", headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def search_library(self, query: str = "", platform: str = "", buyer: str = "", service: str = "", limit: int = 20, __user__: dict = {}, __request__=None) -> str:
        """
        Search the historical library of all scanned assignments with filters.
        :param query: Free text search
        :param platform: Filter by platform (e.g. 'TenderNED')
        :param buyer: Filter by buying organization
        :param service: Filter by service type
        :param limit: Max results (default 20)
        :return: Matching assignments with full details
        """
        params: dict = {"limit": limit}
        if query:
            params["q"] = query
        if platform:
            params["platform"] = platform
        if buyer:
            params["buyer"] = buyer
        if service:
            params["service"] = service
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.opdrachten_api_url}/api/library", params=params, headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def get_stats(self, __user__: dict = {}, __request__=None) -> str:
        """
        Get assignment pipeline statistics — counts per stage, conversion rates, activity summary.
        :return: Statistics overview of the opdrachten pipeline
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.opdrachten_api_url}/api/stats", headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def accept_inbox_item(self, item_id: str, __user__: dict = {}, __request__=None) -> str:
        """
        Accept an inbox item and move it to the pipeline (interesse stage).
        :param item_id: ID of the inbox item to accept
        :return: Updated item now in the pipeline
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.post(f"{self.valves.opdrachten_api_url}/api/inbox/{item_id}/accept", headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def move_pipeline_stage(self, item_id: str, stage: str, __user__: dict = {}, __request__=None) -> str:
        """
        Move a pipeline item to a different stage.
        :param item_id: ID of the pipeline item
        :param stage: Target stage: 'interesse', 'offerte', 'gegund', 'actief', 'afgerond', 'afgewezen', or 'genegeerd'
        :return: Updated pipeline item
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.post(f"{self.valves.opdrachten_api_url}/api/pipeline/{item_id}/stage", json={"stage": stage}, headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text
