from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


class SearchCatalogArgs(BaseModel):
    query: str = Field(
        description=(
            "Primary natural-language query capturing the user's core search intent. "
            "Must be a complete, well-formed sentence or concise phrase."
        ),
        min_length=1,
    )

    expansions: list[str] = Field(
        default_factory=list,
        description=(
            "0 to 5 short alternative phrasings of the SAME search intent. "
            "Each expansion must:\n"
            "- Preserve the original meaning\n"
            "- Not introduce new topics\n"
            "- Be under 12 words\n"
            "- Be a single phrase (no explanations)\n"
            "- Not repeat the original query verbatim\n"
            "Return an empty list if no meaningful variations exist."
        ),
        max_length=5,
    )


class SearchCatalogTool(BaseTool):
    name: str = "search_catalog"
    description: str = "Search catalog assets by query + semantic expansions."
    args_schema: type[BaseModel] = SearchCatalogArgs

    def _run(
        self,
        query: str,
        expansions: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> list[dict[str, str]]:
        prepared_queries = self._prepare_query_expansions(
            query=query,
            expansions=expansions,
            keywords=keywords,
        )
        if not prepared_queries:
            return []

        logger.info(f"Prepared query expansions for search: {prepared_queries}")

        catalog = get_catalog()
        semantic_search_list, dataplane_list, policy_list = self._filter_catalog(catalog)

        logger.info(f"Semantic search list: {semantic_search_list}")

        description_map = {
            item["asset_id"]: item.get("description", "")
            for item in semantic_search_list
        }

        filtered_list = self._semantic_search(
            semantic_search_list, prepared_queries, os.getenv("EMBEDDING_MODEL", "")
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
        self, semantic_search_list: list[dict[str, Any]], queries: list[str], model: str
    ) -> list[str]:
        if not semantic_search_list or not queries:
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
            texts=queries,
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
        if not query_embeddings or not document_embeddings:
            return []
        similarity_matrix = cosine_similarity(document_embeddings, query_embeddings)
        return [float(max(row)) for row in similarity_matrix]

    def _prepare_query_expansions(
        self,
        query: str | None,
        expansions: list[str] | None,
        keywords: list[str] | None,
    ) -> list[str]:
        # Backward compatibility:
        # if legacy `keywords` is sent, first item is treated as `query`
        # and the next items as expansions.
        raw_query = query or ""
        raw_expansions = expansions or []
        if (not raw_query.strip()) and keywords:
            raw_query = str(keywords[0])
            raw_expansions = [str(item) for item in keywords[1:]]

        unique_queries: list[str] = []
        seen: set[str] = set()

        for raw_text in [raw_query, *raw_expansions]:
            text = str(raw_text).strip()
            if not text:
                continue

            lowered = text.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            unique_queries.append(text)
            if len(unique_queries) >= 6:
                break

        return unique_queries

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


def search_catalog(
    query: str | list[str], expansions: list[str] | None = None
) -> list[dict[str, str]]:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    if isinstance(query, list):
        legacy_keywords = query
        if not legacy_keywords:
            return []
        return search_catalog_tool._run(
            query=str(legacy_keywords[0]),
            expansions=[str(item) for item in legacy_keywords[1:]],
        )
    return search_catalog_tool._run(query=query, expansions=expansions)
