"""
title: Ruimtemeesters Databank
description: Search policy documents, query the knowledge graph, and manage beleidsscan queries in the Ruimtemeesters Databank.
author: Ruimtemeesters
version: 2.0.0
requirements: httpx
"""

import httpx
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        databank_api_url: str = Field(default="http://host.docker.internal:4000", description="Base URL of the Databank API")
        api_key: str = Field(default="", description="Fallback service API key if no Clerk token")
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

    async def search_beleidsdocumenten(self, query: str, location: str = "", document_type: str = "", limit: int = 10, __user__: dict = {}, __request__=None) -> str:
        """
        Search for Dutch policy documents (beleidsstukken) using hybrid keyword and semantic search.
        :param query: Search query in Dutch, e.g. 'luchtkwaliteit' or 'woningbouw Den Haag'
        :param location: Optional municipality or region name to filter by
        :param document_type: Optional document type filter
        :param limit: Maximum number of results (default 10)
        :return: Search results with document titles, summaries, and metadata
        """
        params = {"q": query, "limit": limit}
        if location:
            params["location"] = location
        if document_type:
            params["documentType"] = document_type
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.databank_api_url}/api/search", params=params, headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def get_knowledge_graph(self, entity_id: str = "", __user__: dict = {}, __request__=None) -> str:
        """
        Query the Databank knowledge graph to explore relationships between policies, topics, and municipalities.
        :param entity_id: Optional specific entity ID to get with its neighbors. Leave empty for overview.
        :return: Knowledge graph data with entities and relationships
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            if entity_id:
                resp = await client.get(f"{self.valves.databank_api_url}/api/knowledge-graph/entity/{entity_id}", headers=self._auth_headers(__request__))
            else:
                resp = await client.get(f"{self.valves.databank_api_url}/api/knowledge-graph", params={"limit": 50}, headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def get_document(self, document_id: str, __user__: dict = {}, __request__=None) -> str:
        """
        Get the full details of a specific canonical document from the Databank.
        :param document_id: The document ID to retrieve
        :return: Full document with metadata, content, and related entities
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.databank_api_url}/api/canonical-documents/{document_id}", headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def list_queries(self, __user__: dict = {}, __request__=None) -> str:
        """
        List the user's beleidsscan queries (policy scan searches).
        :return: List of queries with their status and results
        """
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.get(f"{self.valves.databank_api_url}/api/queries", headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text

    async def create_query(self, search_text: str, location: str = "", __user__: dict = {}, __request__=None) -> str:
        """
        Start a new beleidsscan query to search for and analyze policy documents.
        :param search_text: The policy topic to search for, e.g. 'luchtkwaliteit maatregelen'
        :param location: Optional municipality or region to scope the search
        :return: Created query with ID and initial status
        """
        body = {"searchText": search_text}
        if location:
            body["location"] = location
        async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
            resp = await client.post(f"{self.valves.databank_api_url}/api/queries", json=body, headers=self._auth_headers(__request__))
            resp.raise_for_status()
            return resp.text
