from __future__ import annotations

import logging
import os
from typing import Annotated, Any

import requests
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

from edc_agent.cp.lib.transferAsset import get_catalog

logger = logging.getLogger(__name__)

_COSINE_GATE = 0.40
_MIN_GAP_RATIO = 0.30
_MIN_ABSOLUTE_GAP = 0.05
_FALLBACK_TOP_N = 20


class SearchCatalogArgs(BaseModel):
    queries: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=200)]],
        Field(
            description=(
                "Semantically diverse search queries derived from the user's request, optimized for "
                "a vector/semantic search engine. Generate between 4 and 8 entries.\n\n"
                "LANGUAGE RULE: produce the expansions in the SAME language as the user's original query. "
                "EXCEPTION: if a technical term, standard name, acronym, or domain-specific concept is "
                "predominantly used in English in the relevant technical or scientific literature, include "
                "AT LEAST ONE expansion using the English term alongside the native-language expansions. "
                "This improves semantic recall when catalog descriptions are written in English or mix "
                "languages.\n\n"
                "COVERAGE — each entry must add a DIFFERENT semantic angle. Aim to cover:\n"
                "(1) a full-sentence rephrasing of the user's intent;\n"
                "(2) synonyms and alternative names for the main concept;\n"
                "(3) domain-specific or technical terms related to the topic (including English technical "
                "terms when applicable);\n"
                "(4) a broader category the topic belongs to — important when catalog descriptions are "
                "written at a higher level of abstraction than the user's query;\n"
                "(5) a more specific subtopic, use case, or application scenario;\n"
                "(6) if the query requires a COMBINATION of attributes (A and B), include at least one "
                "expansion for EACH component independently, plus one for the combination — otherwise "
                "assets covering only one component would not be retrieved;\n"
                "(7) if the query is CONTEXTUAL (the user's need is implied rather than expressed as direct "
                "keywords), include expansions describing the downstream use case, related metrics, or "
                "typical data products associated with the request.\n\n"
                "STYLE:\n"
                "- Prefer descriptive phrases (3–8 words) over single words.\n"
                "- Do not invent technical jargon unrelated to the user's request.\n"
                "- Avoid redundancy — rephrasings that differ only in word order do not count as different "
                "angles.\n\n"
                "EXAMPLE — user asks in English: 'I need temperature sensor data':\n"
                '["IoT temperature sensor readings", "environmental monitoring dataset", '
                '"thermal measurement time series", "climate sensor telemetry", '
                '"ambient temperature observations", "indoor temperature logs"]'
            ),
            min_length=2,
        ),
    ]


class SearchCatalogTool(BaseTool):
    name: str = "search_catalog_tool"
    description: str = (
        "Searches the EDC catalog for assets matching the user's intent.\n\n"
        "INPUT: a list of 2–8 semantically diverse search queries (see `queries` for construction rules).\n\n"
        "OUTPUT: a list of {asset_id, description} dicts, ranked by semantic relevance to the queries. "
        "The list may be empty when no asset is sufficiently relevant — an empty result is a valid "
        "answer, not an error."
    )
    args_schema: type[BaseModel] = SearchCatalogArgs

    def _run(self, queries: list[str]) -> list[dict[str, str]]:
        logger.info("search_catalog queries: %s", queries)
        prepared_queries = self._prepare_keywords(queries)
        if not prepared_queries:
            return []

        catalog = get_catalog()
        logger.debug("search_catalog raw catalog: %s", catalog)
        assets = self._extract_assets(catalog)

        try:
            ranked = self._semantic_search(assets, prepared_queries, os.getenv("EMBEDDING_MODEL", ""))
        except Exception as exc:
            logger.error("search_catalog semantic search failed: %s", exc)
            return []
        selected = self._dynamic_cutoff(ranked)

        return [
            {"asset_id": asset_id, "description": description}
            for asset_id, description, _ in selected
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
    ) -> list[tuple[str, str, float]]:
        """Returns assets passing the cosine gate, sorted by score descending: (asset_id, description, score)."""
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
        similarities = self._avg_cosine_similarities(query_embeddings, document_embeddings)

        mean = sum(similarities) / len(similarities)
        variance = sum((s - mean) ** 2 for s in similarities) / len(similarities)
        std = variance ** 0.5

        logger.info("search_catalog cosine scores (mean=%.4f, std=%.4f):", mean, std)
        passed = []
        for item, score in zip(assets, similarities):
            z_score = (score - mean) / std if std > 0 else 0.0
            above_gate = score >= _COSINE_GATE
            status = "PASS" if above_gate else "FAIL"
            logger.info(
                "  [%s] score=%.4f  z=%.2f  %-40s  %s",
                status,
                score,
                z_score,
                item["asset_id"],
                item.get("description", "")[:60],
            )
            if above_gate:
                passed.append((item, score))

        passed.sort(key=lambda x: x[1], reverse=True)
        return [(item["asset_id"], item.get("description", ""), score) for item, score in passed]

    def _dynamic_cutoff(
        self, ranked: list[tuple[str, str, float]]
    ) -> list[tuple[str, str, float]]:
        if len(ranked) <= 1:
            return ranked

        scores = [score for _, _, score in ranked]
        score_range = scores[0] - scores[-1]
        gaps = [scores[i] - scores[i + 1] for i in range(len(scores) - 1)]
        max_gap = max(gaps)
        relative_gap = (max_gap / score_range) if score_range > 0 else 0.0

        cut = gaps.index(max_gap) + 1
        if relative_gap >= _MIN_GAP_RATIO and max_gap >= _MIN_ABSOLUTE_GAP and cut >= 2:
            logger.info(
                "search_catalog dynamic cutoff at position %d (gap=%.4f, relative=%.2f)",
                cut, max_gap, relative_gap,
            )
            return ranked[:cut]

        cut = min(_FALLBACK_TOP_N, len(ranked))
        logger.info(
            "search_catalog no significant gap (relative=%.2f < %.2f), fallback top-%d",
            relative_gap, _MIN_GAP_RATIO, cut,
        )
        return ranked[:cut]

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
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError("Ollama embedding response size mismatch.")
        return embeddings

    def _avg_cosine_similarities(
        self, query_embeddings: list[list[float]], document_embeddings: list[list[float]]
    ) -> list[float]:
        # matrix shape: (n_queries, n_docs)
        similarity_matrix = sklearn_cosine_similarity(query_embeddings, document_embeddings)
        return similarity_matrix.mean(axis=0).tolist()

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
