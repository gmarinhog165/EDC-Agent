import logging
from time import time
import os
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from edc_agent.cp.lib.transferAsset import (
    get_catalog,
    negotiate_contract,
    transfer_to_s3
)

logger = logging.getLogger(__name__)


class FetchItemDataArgs(BaseModel):
    item_id: str = Field(description="Asset ID selected for data exchange.")


class FetchItemDataTool(BaseTool):
    name: str = "fetch_item_data"
    description: str = "Fetch data exchange details for a specific asset ID."
    args_schema: type[BaseModel] = FetchItemDataArgs

    def _run(self, item_id: str) -> dict[str, object]:
        try:
            # Obter detalhes do asset selecionado (política, counterpartyId, counterPartyAdress)
            catalogs = get_catalog()

            ## Extrair estes campos para variaveis a partir dos catalogs
            counter_party_address, counter_party_id, policy = None, None, None
            for catalog in catalogs:
                for dataset in catalog["dcat:dataset"]:
                    if dataset["@id"] == item_id:
                        policy = dataset.get("odrl:hasPolicy", None)
                        break
                if policy:
                    counter_party_address = catalog.get("originator", None)
                    counter_party_id = catalog.get("dspace:participantId", None)
                    break

            # Validação caso haja algum erro
            if not policy or not counter_party_address or not counter_party_id:
                return {
                    "status": "error",
                    "item_id": item_id,
                    "message": "Asset not found in catalog or missing policy/counter-party details.",
                }


            # Iniciar negociação
            contract_id = negotiate_contract(
                asset_id=item_id,
                counter_party_address=counter_party_address,
                counter_party_id=counter_party_id,
                policy=policy,
            )

            ## Validação caso haja algum erro
            if not contract_id:
                return {
                    "status": "error",
                    "item_id": item_id,
                    "message": "Contract negotiation failed.",
                }

            # Iniciar transferência
            filename = f"{item_id}_{int(time())}.json"
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

            ## Validação caso haja algum erro
            if not transfer_result:
                return {
                    "status": "error",
                    "item_id": item_id,
                    "contract_id": contract_id,
                    "message": "Transfer failed.",
                }

            ## Retornar detalhes da transferência para o agente
            return {
                "status": "success",
                "item_id": item_id,
                "contract_id": contract_id,
                "transfer_id": transfer_result.get("@id") or transfer_result.get("id"),
                "message": "Negotiation and transfer completed successfully.",
            }
        except Exception as exc:  # pragma: no cover
            return {
                "status": "error",
                "item_id": item_id,
                "message": "Unexpected error while fetching item data.",
                "details": str(exc),
            }


fetch_item_data_tool = FetchItemDataTool()

def fetch_item_data(item_id: str) -> dict[str, object]:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    return fetch_item_data_tool._run(item_id=item_id)
