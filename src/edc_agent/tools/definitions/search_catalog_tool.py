from __future__ import annotations

import logging
import os
from typing import Annotated, Any

import requests
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from edc_agent.cp.lib.transferAsset import get_catalog

logger = logging.getLogger(__name__)


class SearchCatalogArgs(BaseModel):
    queries: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=200)]],
        Field(
            description=(
                "Semantically diverse search queries derived from the user's request. "
                "Generate between 2 and 8 entries covering: "
                "(1) a full-sentence rephrasing of the user's intent, "
                "(2) synonyms and alternative names for the main concept, "
                "(3) domain-specific or technical terms related to the topic, "
                "(4) a broader category the topic belongs to, "
                "(5) a more specific subtopic or use case. "
                "Prefer descriptive phrases over single words. "
                "Avoid redundancy — each entry must add a different semantic angle. "
                "Do not invent technical jargon unrelated to the user's request. "
                'Example — user asks "I need temperature sensor data": '
                '["IoT temperature sensor readings", "environmental monitoring data", '
                '"thermal measurement dataset", "climate sensor telemetry", "sensor time series"].'
            ),
            min_length=2,
            max_length=8,
        ),
    ]


class SearchCatalogTool(BaseTool):
    name: str = "search_catalog"
    description: str = "Search catalog assets by topic + related queries."
    args_schema: type[BaseModel] = SearchCatalogArgs

    def _run(self, queries: list[str]) -> list[dict[str, str]]:
        logger.info("search_catalog queries: %s", queries)
        prepared_queries = self._prepare_keywords(queries)
        if not prepared_queries:
            return []

        catalog = get_catalog()
        logger.info("search_catalog raw catalog: %s", catalog)
        semantic_search_list = self._extract_assets(catalog)

        filtered_list = self._semantic_search(
            semantic_search_list, prepared_queries, os.getenv("EMBEDDING_MODEL", "")
        )

        return [
            {
                "asset_id": asset_id,
                "description": next(
                    (item["description"] for item in semantic_search_list if item["asset_id"] == asset_id),
                    "",
                ),
            }
            for asset_id in filtered_list
        ]

    def _extract_assets(self, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        for item in catalog:
            for asset in item["dcat:dataset"]:
                assets.append({
                    "asset_id": asset["@id"],
                    "description": asset.get("description", ""),
                })
        return assets

    def _semantic_search(
        self, assets: list[dict[str, Any]], queries: list[str], model: str
    ) -> list[str]:
        if not assets or not queries:
            return []
        if not model:
            raise ValueError("EMBEDDING_MODEL must be configured for semantic search.")
        if ":" not in model:
            raise ValueError(
                "EMBEDDING_MODEL must use Ollama format 'name:tag' "
                "(example: qwen3-embedding:0.6b)."
            )

        descriptions = [item.get("description", "") for item in assets]
        query_embeddings = self._encode_with_ollama(model=model, texts=queries, is_query=True)
        document_embeddings = self._encode_with_ollama(model=model, texts=descriptions, is_query=False)
        max_similarities = self._max_cosine_similarities(
            query_embeddings=query_embeddings,
            document_embeddings=document_embeddings,
        )

        return [
            item.get("asset_id")
            for item, score in zip(assets, max_similarities, strict=False)
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

        return dot / ((left_norm**0.5) * (right_norm**0.5))

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
            if len(unique_keywords) >= 8:
                break

        return unique_keywords


search_catalog_tool = SearchCatalogTool()


def search_catalog(queries: list[str]) -> list[dict[str, str]]:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    return search_catalog_tool._run(queries=queries)
