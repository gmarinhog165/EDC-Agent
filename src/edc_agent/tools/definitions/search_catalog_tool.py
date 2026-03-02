from __future__ import annotations

import os
from typing import Any

import requests
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from edc_agent.cp.lib.transferAsset import (
    check_available_dataplanes,
    check_policy_verification,
    get_catalog,
)


class SearchCatalogArgs(BaseModel):
    keywords: list[str] = Field(
        description=(
            "List where the first element is the main topic from the user query, "
            "followed by up to 5 related keywords." # LLM gera isto
        ),
        min_length=1,
        max_length=6,
    )


class SearchCatalogTool(BaseTool):
    name: str = "search_catalog"
    description: str = "Search catalog assets by topic + related keywords."
    args_schema: type[BaseModel] = SearchCatalogArgs

    def _run(self, keywords: list[str]) -> list[dict[str, str]]:
        prepared_keywords = self._prepare_keywords(keywords)
        if not prepared_keywords:
            return []

        catalog = get_catalog()
        semantic_search_list, dataplane_list, policy_list = self._filter_catalog(catalog)

        description_map = {
            item["asset_id"]: item.get("description", "")
            for item in semantic_search_list
        }

        filtered_list = self._semantic_search(
            semantic_search_list, prepared_keywords, os.getenv("EMBEDDING_MODEL", "")
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
        self, semantic_search_list: list[dict[str, Any]], keywords: list[str], model: str
    ) -> list[str]:
        if not semantic_search_list or not keywords:
            return []
        if not model:
            raise ValueError("EMBEDDING_MODEL must be configured for semantic search.")
        if ":" not in model:
            raise ValueError(
                "EMBEDDING_MODEL must use Ollama format 'name:tag' "
                "(example: qwen3-embedding:0.6b)."
            )

        descriptions = [item.get("description", "") for item in semantic_search_list]
        query_embeddings = self._encode_with_ollama(
            model=model,
            texts=keywords,
            is_query=True,
        )
        document_embeddings = self._encode_with_ollama(
            model=model,
            texts=descriptions,
            is_query=False,
        )
        max_similarities = self._max_cosine_similarities(
            query_embeddings=query_embeddings,
            document_embeddings=document_embeddings,
        )

        return [
            item.get("asset_id")
            for item, score in zip(semantic_search_list, max_similarities, strict=False)
            if float(score) > 0.5
        ]

    def _encode_with_ollama(
        self, model: str, texts: list[str], is_query: bool
    ) -> list[list[float]]:
        base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv(
            "LLM_BASE_URL", "http://localhost:11434"
        )
        endpoint = f"{base_url.rstrip('/')}/api/embed"
        # Approximation of query/document prompts for embedding models that benefit from query framing.
        inputs = [f"query: {text}" for text in texts] if is_query else texts
        response = requests.post(
            endpoint,
            json={"model": model, "input": inputs},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError("Ollama embedding response size mismatch.")
        return embeddings

    def _max_cosine_similarities(
        self, query_embeddings: list[list[float]], document_embeddings: list[list[float]]
    ) -> list[float]:
        max_scores: list[float] = []
        for document_embedding in document_embeddings:
            best_score = max(
                self._cosine_similarity(query_embedding, document_embedding)
                for query_embedding in query_embeddings
            )
            max_scores.append(float(best_score))
        return max_scores

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("Embedding dimensions do not match.")

        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for left_value, right_value in zip(left, right, strict=False):
            dot += left_value * right_value
            left_norm += left_value * left_value
            right_norm += right_value * right_value

        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0

        return dot / ((left_norm ** 0.5) * (right_norm ** 0.5))

    def _prepare_keywords(self, keywords: list[str]) -> list[str]:
        unique_keywords: list[str] = []
        seen: set[str] = set()

        for raw_keyword in keywords:
            keyword = str(raw_keyword).strip()
            if not keyword:
                continue

            lowered_keyword = keyword.lower()
            if lowered_keyword in seen:
                continue

            seen.add(lowered_keyword)
            unique_keywords.append(keyword)
            if len(unique_keywords) >= 6:
                break

        return unique_keywords

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


def search_catalog(keywords: list[str]) -> list[dict[str, str]]:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    return search_catalog_tool._run(keywords=keywords)
