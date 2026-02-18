from __future__ import annotations

import os
from typing import Any

import requests
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from sklearn.metrics.pairwise import cosine_similarity

from edc_agent.cp.lib.transferAsset import (
    check_available_dataplanes,
    check_policy_verification,
    get_catalog,
)


class SearchCatalogArgs(BaseModel):
    query: str = Field(description="User query used to find relevant assets.")


class SearchCatalogTool(BaseTool):
    name: str = "search_catalog"
    description: str = "Search catalog assets by query text."
    args_schema: type[BaseModel] = SearchCatalogArgs

    def _run(self, query: str) -> list[dict[str, str]]:
        catalog = get_catalog()
        semantic_search_list, dataplane_list, policy_list = self._filter_catalog(catalog)

        description_map = {
            item["asset_id"]: item.get("description", "")
            for item in semantic_search_list
        }

        filtered_list = self._semantic_search(
            semantic_search_list, query, os.getenv("EMBEDDING_MODEL", "")
        )

        available_dataplanes = set(check_available_dataplanes() or [])
        dataplane_map = {
            item["asset_id"]: set(item.get("data_address", []))
            for item in dataplane_list
        }

        filtered_list = [
            asset_id
            for asset_id in filtered_list
            if not dataplane_map.get(asset_id, set()).isdisjoint(available_dataplanes)
        ]

        filtered_set = set(filtered_list)
        filtered_policy_list = [
            item for item in policy_list if item.get("asset_id") in filtered_set
        ]
        filtered_list = check_policy_verification(filtered_policy_list)

        return [
            {
                "asset_id": asset_id,
                "description": description_map.get(asset_id, ""),
            }
            for asset_id in filtered_list
        ]

    def _semantic_search(
        self, semantic_search_list: list[dict[str, Any]], query: str, model: str
    ) -> list[str]:
        embedding_url = (
            f"{os.getenv('LLM_BASE_URL', 'http://localhost:11434').rstrip('/')}"
            "/api/embeddings"
        )

        def _get_embedding(text: str) -> list[float]:
            payload = {"model": model, "prompt": text}
            response = requests.post(embedding_url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()["embedding"]

        query_embedding = _get_embedding(query)

        filtered_items: list[str] = []
        for item in semantic_search_list:
            cached_embedding = item.get("embedding")
            if cached_embedding is None:
                cached_embedding = _get_embedding(item.get("description", ""))
                item["embedding"] = cached_embedding

            score = float(cosine_similarity([cached_embedding], [query_embedding])[0][0])
            if score > 0.5:
                filtered_items.append(item.get("asset_id"))

        return filtered_items

    def _filter_catalog(
        self, catalog: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        semantic_search_list: list[dict[str, Any]] = []
        dataplane_list: list[dict[str, Any]] = []
        policy_list: list[dict[str, Any]] = []

        for item in catalog:
            for asset in item["dcat:dataset"]:
                asset_id = asset["@id"]
                asset_description = asset.get("description", "")

                semantic_search_list.append(
                    {"asset_id": asset_id, "description": asset_description}
                )

                temp_dataplanes = []
                for dataplane in asset.get("dcat:distribution"):
                    temp_dataplanes.append(dataplane["dct:format"]["@id"])

                dataplane_list.append(
                    {"asset_id": asset_id, "data_address": temp_dataplanes}
                )
                policy_list.append(
                    {"asset_id": asset_id, "policy": asset.get("odrl:hasPolicy", {})}
                )

        return semantic_search_list, dataplane_list, policy_list


search_catalog_tool = SearchCatalogTool()


def search_catalog(query: str) -> list[dict[str, str]]:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    return search_catalog_tool._run(query=query)
