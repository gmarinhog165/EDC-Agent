from time import time
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

_FETCH_MAX_WORKERS = int(os.getenv("FETCH_MAX_WORKERS", "5"))

from edc_agent.cp.lib.transferAsset import (
    check_asset_exists,
    get_catalog,
    negotiate_contract,
    transfer_to_s3,
)


class FetchItemDataArgs(BaseModel):
    item_ids: list[str] = Field(
        description=(
            "List of asset IDs selected for data exchange. "
            "Pass one or more exact asset IDs; each is fetched independently and "
            "individual failures do not block the others."
        ),
        min_length=1,
    )


def _error(item_id: str, code: str, message: str, **extra) -> dict[str, Any]:
    return {"status": "error", "item_id": item_id, "error_code": code, "message": message, **extra}


def _find_policy(catalogs: list, item_id: str) -> tuple[Optional[Any], Optional[str], Optional[str]]:
    """Return (policy, counter_party_address, counter_party_id) for item_id, or (None, None, None)."""
    for catalog in catalogs:
        datasets = catalog.get("dcat:dataset", [])
        if isinstance(datasets, dict):
            datasets = [datasets]
        for dataset in datasets:
            if dataset.get("@id") == item_id:
                policy = dataset.get("odrl:hasPolicy", None)
                if policy:
                    return (
                        policy,
                        catalog.get("originator", None),
                        catalog.get("dspace:participantId", None),
                    )
    return None, None, None


def _fetch_one(item_id: str, catalogs: Optional[list]) -> dict[str, Any]:
    try:
        existence = check_asset_exists(item_id)
        if existence["exists"] is False:
            return _error(item_id, "unknown_asset", existence["message"])
        if existence["exists"] is None:
            return _error(item_id, "system_error", existence["message"])

        if not catalogs:
            return _error(item_id, "catalog_unavailable",
                          "Não foi possível obter o catálogo do consumer.")

        policy, counter_party_address, counter_party_id = _find_policy(catalogs, item_id)
        if not policy:
            return _error(item_id, "asset_not_in_catalog",
                          f"Asset '{item_id}' existe no provider mas não aparece no catálogo do consumer.")
        if not counter_party_address or not counter_party_id:
            return _error(item_id, "catalog_metadata_missing",
                          "Catálogo não contém originator/participantId para este asset.")

        nego = negotiate_contract(
            asset_id=item_id,
            counter_party_address=counter_party_address,
            counter_party_id=counter_party_id,
            policy=policy,
        )
        if nego["error_code"] is not None:
            return _error(item_id, nego["error_code"], nego["message"])
        contract_id = nego["contract_id"]

        filename = f"{item_id}_{time():.6f}.json"
        transfer_result = transfer_to_s3(
            asset_id=item_id,
            contract_id=contract_id,
            filename=filename,
            region=os.getenv("S3_REGION", "eu-west-1"),
            bucket_name=os.getenv("S3_BUCKET_NAME", "edc-agent-data"),
            counter_party_address=counter_party_address,
            connector_id=counter_party_id,
            endpoint_override=os.getenv("S3_ENDPOINT_OVERRIDE", None),
        )
        if not transfer_result:
            return _error(item_id, "transfer_failed",
                          "Transferência falhou ou excedeu o tempo limite.",
                          contract_id=contract_id)

        return {
            "status": "success",
            "item_id": item_id,
            "contract_id": contract_id,
            "transfer_id": transfer_result.get("@id") or transfer_result.get("id"),
            "message": "Negotiation and transfer completed successfully.",
        }
    except Exception as exc:  # pragma: no cover
        return _error(item_id, "system_error",
                      "Unexpected error while fetching item data.",
                      details=str(exc))


class FetchItemDataTool(BaseTool):
    name: str = "fetch_item_data"
    description: str = (
        "Fetch data for one or more asset IDs. Each ID is processed independently "
        "(best-effort): individual failures are reported per-asset and do not stop "
        "the others. Returns {results: [...per-asset...], summary: {...}}."
    )
    args_schema: type[BaseModel] = FetchItemDataArgs

    def _run(self, item_ids: list[str]) -> dict[str, Any]:
        # Normalize: strip, drop empties, dedupe while preserving order
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw in item_ids:
            if not isinstance(raw, str):
                continue
            asset_id = raw.strip()
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            cleaned.append(asset_id)

        if not cleaned:
            return {
                "results": [],
                "summary": {"total": 0, "succeeded": 0, "failed": 0,
                            "message": "Nenhum asset_id válido foi fornecido."},
            }

        # Fetch catalog once for the whole batch
        try:
            catalogs = get_catalog()
        except Exception as exc:
            catalogs = None
            catalog_error = str(exc)
        else:
            catalog_error = None

        # Short-circuit when catalog is unavailable — no point spinning up workers
        if not catalogs:
            results: list[dict[str, Any]] = [
                _error(asset_id, "catalog_unavailable",
                       f"Catálogo indisponível: {catalog_error}" if catalog_error
                       else "Não foi possível obter o catálogo do consumer.")
                for asset_id in cleaned
            ]
        else:
            results = [None] * len(cleaned)  # type: ignore[list-item]
            max_workers = max(1, min(_FETCH_MAX_WORKERS, len(cleaned)))
            with ThreadPoolExecutor(max_workers=max_workers,
                                    thread_name_prefix="fetch-item") as pool:
                futures = {
                    pool.submit(_fetch_one, asset_id, catalogs): idx
                    for idx, asset_id in enumerate(cleaned)
                }
                for fut in futures:
                    idx = futures[fut]
                    try:
                        results[idx] = fut.result()
                    except Exception as exc:  # safety net — _fetch_one already catches
                        results[idx] = _error(cleaned[idx], "system_error",
                                              "Unexpected error while fetching item data.",
                                              details=str(exc))

        succeeded = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - succeeded
        return {
            "results": results,
            "summary": {"total": len(results), "succeeded": succeeded, "failed": failed},
        }


fetch_item_data_tool = FetchItemDataTool()


def fetch_item_data(item_ids: list[str]) -> dict[str, Any]:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    return fetch_item_data_tool._run(item_ids=item_ids)
