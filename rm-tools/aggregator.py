"""
title: Ruimtemeesters Aggregator
description: Cross-app queries combining Databank policy documents, Geoportaal spatial rules, and knowledge graph data. Context lookups by coordinate or municipality, document search, spatial analysis, solar potential, and graph traversal.
author: Ruimtemeesters
version: 1.0.0
requirements: httpx
"""

import httpx
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        aggregator_api_url: str = Field(
            default="http://localhost:6000",
            description="Base URL of the Aggregator API",
        )
        aggregator_api_key: str = Field(
            default="",
            description="API key for the Aggregator (X-API-Key header)",
        )
        timeout: int = Field(default=30, description="Request timeout in seconds")

    def __init__(self):
        self.valves = self.Valves()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.valves.aggregator_api_key:
            h["X-API-Key"] = self.valves.aggregator_api_key
        return h

    # ── Cross-app context (Databank + Geoportaal combined) ──

    async def context_at_coordinate(
        self,
        lon: float,
        lat: float,
        project_id: int = 0,
        __user__: dict = {},
    ) -> str:
        """
        Get the full context at a geographic coordinate — combines policy documents from the Databank with spatial rules from the Geoportaal in a single query.

        :param lon: Longitude (WGS84), e.g. 4.9041 for Amsterdam
        :param lat: Latitude (WGS84), e.g. 52.3676 for Amsterdam
        :param project_id: Optional Geoportaal project ID for rule filtering
        :return: Documents matching the municipality + spatial rules at that point
        """
        params = {"lon": lon, "lat": lat}
        if project_id:
            params["projectId"] = project_id

        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/context/at",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def context_municipality(
        self,
        municipality_code: str,
        __user__: dict = {},
    ) -> str:
        """
        Get a full municipality overview — combines gemeente info, document counts by type from the Databank, and spatial rules per project from the Geoportaal.

        :param municipality_code: CBS gemeente code in lowercase, e.g. 'gm0363' for Amsterdam or 'gm0344' for Utrecht
        :return: Gemeente details, document breakdown by type, and rules per project
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/context/municipality/{municipality_code}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    # ── Document search (Databank via Aggregator) ──

    async def search_documents(
        self,
        query: str,
        municipality_code: str = "",
        document_type: str = "",
        limit: int = 20,
        __user__: dict = {},
    ) -> str:
        """
        Search policy documents across the Databank with full-text search and filters. Supports spatial filtering by municipality and document type.

        :param query: Search text in Dutch, e.g. 'luchtkwaliteit maatregelen'
        :param municipality_code: Optional CBS code to filter by gemeente, e.g. 'gm0363'
        :param document_type: Optional document type filter
        :param limit: Maximum results (default 20, max 500)
        :return: Ranked search results with document metadata
        """
        body = {"q": query, "limit": min(limit, 500)}
        if municipality_code:
            body["jurisdiction"] = municipality_code
        if document_type:
            body["documentType"] = document_type

        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.post(
                f"{self.valves.aggregator_api_url}/v1/documents/search",
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def get_document_summary(
        self,
        document_id: str,
        __user__: dict = {},
    ) -> str:
        """
        Get a summary of a specific document (first 3 chunks) from the Databank.

        :param document_id: The document UUID
        :return: Document summary text and chunk count
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/documents/{document_id}/summary",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    # ── Spatial queries (Geoportaal via Aggregator) ──

    async def spatial_rules_at_point(
        self,
        lon: float,
        lat: float,
        project_id: int = 1,
        __user__: dict = {},
    ) -> str:
        """
        Get all spatial planning rules (omgevingsregels/DSO artikelen) that apply at a specific coordinate.

        :param lon: Longitude (WGS84)
        :param lat: Latitude (WGS84)
        :param project_id: Geoportaal project ID (default 1)
        :return: Applicable rules with article content, activity names, and location
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/spatial/regels",
                params={"lon": lon, "lat": lat, "projectId": project_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def solar_potential(
        self,
        bbox: str,
        project_id: int = 1,
        __user__: dict = {},
    ) -> str:
        """
        Get solar energy potential for buildings in an area — total capacity, average irradiance, and breakdown by panel profile.

        :param bbox: Bounding box as 'minlon,minlat,maxlon,maxlat' in WGS84, e.g. '4.88,52.36,4.92,52.38'
        :param project_id: Geoportaal project ID (default 1)
        :return: Solar potential summary with total buildings, MWh/year, and profile breakdown
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/spatial/solar",
                params={"bbox": bbox, "projectId": project_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    # ── Knowledge graph (Neo4j via Aggregator) ──

    async def search_knowledge_graph(
        self,
        query: str,
        entity_type: str = "",
        limit: int = 20,
        __user__: dict = {},
    ) -> str:
        """
        Search entities in the knowledge graph by name. Find policies, topics, organizations, and their relationships.

        :param query: Search text for entity names
        :param entity_type: Optional Neo4j label to filter by (e.g. 'Policy', 'Topic', 'Organization')
        :param limit: Maximum results (default 20, max 200)
        :return: Matching entities with their types and properties
        """
        params = {"q": query, "limit": min(limit, 200)}
        if entity_type:
            params["type"] = entity_type

        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/kg/entities",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def get_entity_relations(
        self,
        entity_id: str,
        __user__: dict = {},
    ) -> str:
        """
        Get a knowledge graph entity with all its direct relationships (1-hop neighbors).

        :param entity_id: The entity ID in the knowledge graph
        :return: Entity details and list of related entities with relationship types
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/kg/entity/{entity_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def traverse_graph(
        self,
        start_id: str,
        max_depth: int = 3,
        direction: str = "both",
        __user__: dict = {},
    ) -> str:
        """
        Traverse the knowledge graph from a starting entity, exploring multi-hop relationships.

        :param start_id: Starting entity ID
        :param max_depth: Maximum traversal depth (1-10, default 3)
        :param direction: Relationship direction: 'outgoing', 'incoming', or 'both' (default 'both')
        :return: Discovered paths with nodes and relationship types
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.post(
                f"{self.valves.aggregator_api_url}/v1/kg/traverse",
                json={
                    "startId": start_id,
                    "maxDepth": min(max_depth, 10),
                    "direction": direction,
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text

    async def graph_stats(
        self,
        __user__: dict = {},
    ) -> str:
        """
        Get knowledge graph statistics — total nodes, relationships, and breakdowns by type.

        :return: Graph statistics with node/relationship counts per type
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(
                f"{self.valves.aggregator_api_url}/v1/kg/stats",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.text
