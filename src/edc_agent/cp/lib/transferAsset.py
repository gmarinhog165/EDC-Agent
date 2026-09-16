from datetime import datetime
import json
import os
from edc_agent.cp.env_loader import load_cp_env
from time import sleep
from typing import Dict, Optional, List, Union, Any
import requests
from edc_agent.cp.lib.sendRequests import send_post_request, send_get_request, send_get_request_auth, API_KEY
from edc_agent.cp.reqCatalog.RequestCatalogBuilder import RequestCatalogBuilder
from edc_agent.cp.negotiation.NegotiationBuilder import NegotiationBuilder
from edc_agent.cp.transfer.TransferBuilder import TransferBuilder
from edc_agent.cp.transfer.HTTPDataDestinationBuilder import HTTPDataDestinationBuilder
from edc_agent.cp.transfer.MongoDataDestinationBuilder import MongoDataDestinationBuilder
from edc_agent.cp.transfer.AmazonS3DataDestinationBuilder import AmazonS3DataDestinationBuilder

load_cp_env()

def check_asset_exists(asset_id: str) -> Dict[str, Any]:
    """
    Verifica se o asset existe no provider antes de iniciar negociação.

    Returns dict with:
      - "exists": bool | None  (None se não foi possível determinar)
      - "error_code": "unknown_asset" | "system_error" | None
      - "message": str
    """
    host_provider = os.getenv("HOST_PROVIDER", "")
    if not host_provider:
        return {"exists": None, "error_code": "system_error", "message": "HOST_PROVIDER não configurado."}

    url = f"{host_provider}/api/management/v3/assets/{asset_id}"
    headers = {"X-Api-Key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        if resp.status_code == 200:
            return {"exists": True, "error_code": None, "message": "Asset encontrado."}
        if resp.status_code == 404:
            return {"exists": False, "error_code": "unknown_asset", "message": f"Asset '{asset_id}' não existe no provider."}
        return {
            "exists": None,
            "error_code": "system_error",
            "message": f"Resposta inesperada do provider (status {resp.status_code}).",
        }
    except requests.exceptions.RequestException as e:
        return {"exists": None, "error_code": "system_error", "message": f"Falha ao contactar provider: {e}"}


def get_catalog() -> Dict[str, str]: # retorna um dicionário com asset_id e policy_id
    query_spec = {
        "@context": [
            "https://w3id.org/edc/connector/management/v0.0.1"
        ],
        "@type": "QuerySpec"
    }
    
    catalog_query_url = os.getenv("CONSUMER_CATALOG_QUERY_URL")
    response = send_post_request(catalog_query_url, "/api/catalog/v1alpha/catalog/query", json.dumps(query_spec))
                
    return response


def negotiate_contract(
    asset_id: str,
    policy: Dict[str, Any],
    counter_party_address: str,
    counter_party_id: str,
    max_retries: int = 10,
    retry_interval: int = 2,
) -> Dict[str, Any]:
    """
    Negocia um contrato. Devolve dict com:
      - "contract_id": str | None
      - "error_code": None | "policy_denied" | "negotiation_timeout" | "negotiation_failed" | "system_error"
      - "message": str
    """

    nego = NegotiationBuilder()\
        .with_policy(policy)\
        .with_counter_party_address(counter_party_address)\
        .with_counter_party_id(counter_party_id)\
        .with_asset_id(asset_id)\
        .build()

    print(nego.to_json())

    host_consumer = os.getenv("HOST_CONSUMER", "")
    response = send_post_request(
        host_consumer,
        "/api/management/v3/contractnegotiations",
        nego.to_json()
    )

    if not isinstance(response, dict):
        return {"contract_id": None, "error_code": "system_error",
                "message": "Sem resposta do consumer ao iniciar negociação."}

    negotiation_id = response.get('@id')
    if not negotiation_id:
        return {"contract_id": None, "error_code": "negotiation_failed",
                "message": "Resposta do consumer não contém ID de negociação."}

    print(f"Iniciada negociação com ID: {negotiation_id}")

    last_state = None
    for attempt in range(max_retries):
        print(f"Verificando estado da negociação (tentativa {attempt+1}/{max_retries})...")

        endpoint = f"/api/management/v3/contractnegotiations/{negotiation_id}"
        ret = send_get_request(host_consumer, endpoint)

        if not ret:
            print(f"Falha ao obter status da negociação na tentativa {attempt+1}.")
            sleep(retry_interval)
            continue

        last_state = ret.get('state')
        print(f"Estado atual: {last_state}")

        if last_state == "FINALIZED":
            contract_agreement_id = ret.get('contractAgreementId')
            if contract_agreement_id:
                return {"contract_id": contract_agreement_id, "error_code": None,
                        "message": "Negociação finalizada com sucesso."}
        elif last_state in ["ERROR", "TERMINATED"]:
            return {"contract_id": None, "error_code": "policy_denied",
                    "message": f"Negociação rejeitada pelo provider (estado: {last_state})."}

        sleep(retry_interval)

    return {"contract_id": None, "error_code": "negotiation_timeout",
            "message": f"Negociação não finalizou em {max_retries * retry_interval}s (último estado: {last_state})."}


def transfer_to_http(
    asset_id: str,
    contract_id: str,
    counter_party_address: str,
    connector_id: str,
    max_retries: int = 10,
    retry_interval: int = 2,
):
    http_transfer = TransferBuilder().with_asset_id(asset_id).with_contract_id(contract_id) \
        .with_counter_party_address(counter_party_address).with_connector_id(connector_id) \
        .with_transfer_type("HttpData-PULL") \
        .with_data_destination(
            HTTPDataDestinationBuilder() \
            .with_type("HttpProxy")
        ) \
        .build()
    
    #print(http_transfer.to_json())
    
    response = send_post_request(
        os.getenv("HOST_CONSUMER", ""),
        "/api/management/v3/transferprocesses", 
        http_transfer.to_json()
    )
    
    # Verificar se a resposta contém o ID da transferência
    transfer_id = response.get('@id')
    if not transfer_id:
        print("Falha ao obter ID de transferência.")
        return False
    
    print(f"Iniciada transferência HTTP com ID: {transfer_id}")

    # HTTP non-finite nunca avança além de STARTED — aceitamos STARTED como sucesso
    return wait_for_transfer_completion(transfer_id, max_retries, retry_interval, accept_started=True)

def http_download_data(transfer_id):
    print(f"Download de dados para Transfer ID: {transfer_id}")
    ## Get EDR DataAddress for TransferID
    host_consumer = os.getenv("HOST_CONSUMER", "")
    endpoint = f"/api/management/v3/edrs/{transfer_id}/dataaddress"
    response = send_get_request(host_consumer, endpoint)

    auth = response.get("authorization")

    ## Download Data from Public API
    print(f"Download de dados do EDR com autorização: {auth}\n para o ID: {transfer_id}")

    host_api = os.getenv("PUBLIC_API", "")
    endpoint = "/api/public"
    response = send_get_request_auth(host_api, endpoint, auth)
    return response

    


def transfer_to_mongo(asset_id: str, contract_id: str, filename: str,
                     connection_string: str, collection: str, database: str,
                     counter_party_address: str, connector_id: str,
                     max_retries: int = 10, retry_interval: int = 2):
    mongo_transfer = TransferBuilder().with_asset_id(asset_id).with_contract_id(contract_id) \
        .with_counter_party_address(counter_party_address).with_connector_id(connector_id) \
        .with_transfer_type("MongoDB-PUSH") \
        .with_data_destination(
            MongoDataDestinationBuilder().with_connection_string(connection_string)\
            .with_filename(filename).with_collection(collection).with_database(database)
        ) \
        .build()
    
    response = send_post_request(
        os.getenv("HOST_CONSUMER", ""),
        "/api/management/v3/transferprocesses", 
        mongo_transfer.to_json()
    )
    
    # Verificar se a resposta contém o ID da transferência
    transfer_id = response.get('@id')
    if not transfer_id:
        print("Falha ao obter ID de transferência para MongoDB.")
        return False
    
    print(f"Iniciada transferência MongoDB com ID: {transfer_id}")
    
    # Esperar pela conclusão da transferência
    return wait_for_transfer_completion(transfer_id, max_retries, retry_interval)


def transfer_to_s3(asset_id: str, contract_id: str, filename: str,
                  region: str, bucket_name: str, counter_party_address: str,
                  connector_id: str, endpoint_override: str = None,
                  max_retries: int = None, retry_interval: int = None):
    # S3 PUSH precisa de janela mais ampla — o dataplane pode demorar minutos
    # sob carga. Defaults: 60 tentativas × 3 s = 180 s. Override via env.
    if max_retries is None:
        max_retries = int(os.getenv("S3_TRANSFER_MAX_RETRIES", "60"))
    if retry_interval is None:
        retry_interval = int(os.getenv("S3_TRANSFER_RETRY_INTERVAL", "3"))
    s3_builder = AmazonS3DataDestinationBuilder()\
        .with_region(region)\
        .with_bucket_name(bucket_name)\
        .with_object_name(datetime.now().strftime('%Y-%m-%d_%H-%M-%S.%f') + f"-{filename}")\
    
    if endpoint_override:
        s3_builder.with_endpoint_override(endpoint_override)
        
    s3_transfer = TransferBuilder().with_asset_id(asset_id).with_contract_id(contract_id) \
        .with_counter_party_address(counter_party_address).with_connector_id(connector_id) \
        .with_transfer_type("AmazonS3-PUSH") \
        .with_data_destination(s3_builder) \
        .build()
    
    print(s3_transfer.to_json())
    
    response = send_post_request(
        os.getenv("HOST_CONSUMER", ""),
        "/api/management/v3/transferprocesses", 
        s3_transfer.to_json()
    )

    # Verificar se a resposta contém o ID da transferência
    if response is None:
        print("S3 transfer failed: response is None")
        return None

    transfer_id = response.get('@id')
    if not transfer_id:
        print("Falha ao obter ID de transferência para S3.")
        return None
    
    print(f"Iniciada transferência S3 com ID: {transfer_id}")
    
    # Esperar pela conclusão da transferência
    return wait_for_transfer_completion(transfer_id, max_retries, retry_interval)

def wait_for_transfer_completion(transfer_id: str, max_retries: int = 10, retry_interval: int = 2,
                                  accept_started: bool = False):
    """
    Aguarda conclusão de uma transferência.

    accept_started=True  → STARTED conta como sucesso (HTTP non-finite, que nunca avança além de STARTED).
    accept_started=False → só COMPLETED/FINALIZED contam como sucesso (push transfers como S3/Mongo).
    """
    host_consumer = os.getenv("HOST_CONSUMER", "")
    success_states = {"COMPLETED", "FINALIZED"}
    if accept_started:
        success_states.add("STARTED")

    for attempt in range(max_retries):
        print(f"Verificando estado da transferência (tentativa {attempt+1}/{max_retries})...")

        endpoint = f"/api/management/v3/transferprocesses/{transfer_id}"
        ret = send_get_request(host_consumer, endpoint)

        if not ret:
            print(f"Falha ao obter status da transferência na tentativa {attempt+1}.")
            sleep(retry_interval)
            continue

        state = ret.get('state')
        print(f"Estado atual da transferência: {state}")

        if state in success_states:
            print(f"Transferência concluída com sucesso. Transfer ID: {transfer_id}")
            return ret
        elif state in ["ERROR", "TERMINATED", "FAILED"]:
            print(f"Transferência falhou com estado: {state}")
            return None

        sleep(retry_interval)

    print("Tempo limite excedido para conclusão da transferência.")
    return None

def check_asset_in_catalog(asset_id: str, catalog: Dict[str, str]) -> Optional[str]:
    """
    Verifica se um asset está no catálogo e retorna seu policy_id se disponível.
    
    Args:
        asset_id: ID do asset a verificar
        catalog: Dicionário de assets e policies
        
    Returns:
        policy_id se o asset existe, None caso contrário
    """
    if asset_id in catalog:
        return catalog[asset_id]
    return None

def check_available_dataplanes() -> Optional[List[str]]:
    """
    Verifica os dataplanes disponíveis no ambiente.
    
    Returns:
        Lista de dataplanes disponíveis ou None em caso de falha
    """
    host_consumer = os.getenv("HOST_CONSUMER", "")
    endpoint = "/api/management/v3/dataplanes"
    
    response = send_get_request(host_consumer, endpoint)
    
    if response:
        return response[0].get('allowedTransferTypes', [])
    
    print("Falha ao obter dataplanes disponíveis.")
    return None


def check_policy_verification(policy_list: List[Dict[str, Any]]) -> List[str]:
    """
    Valida policies dos assets filtrados no endpoint de policy verification.

    Lê os seguintes valores do .env:
      - PARTICIPANT_ID
      - POLICY_SCOPES (csv: scope1,scope2,...)
      - POLICY_VERIFICATION_ENDPOINT (opcional)
    """
    host_consumer = os.getenv("HOST_CONSUMER", "")
    endpoint = "/api/management/v3/contractnegotiations/validate"
    participant_id = os.getenv("PARTICIPANT_ID", "")
    scopes = [s.strip() for s in os.getenv("POLICY_SCOPES", "").split(",") if s.strip()]

    if not host_consumer or not participant_id or not scopes:
        print("Faltam variáveis de ambiente para verificar policy (HOST_CONSUMER, PARTICIPANT_ID, POLICY_SCOPES).")
        return []

    verified_assets: List[str] = []

    for item in policy_list:
        asset_id = item.get("asset_id")
        raw_policy = item.get("policy", {})
        if not asset_id:
            continue
        if not raw_policy:
            continue

        body = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                "odrl": "http://www.w3.org/ns/odrl/2/",
            },
            "@type": "ValidateContractPolicyRequest",
            "participantId": participant_id,
            "scopes": scopes,
            "policy": raw_policy,
        }

        response = send_post_request(host_consumer, endpoint, json.dumps(body))
        if not isinstance(response, dict):
            continue

        is_valid = bool(response.get("isValid", response.get("valid", False)))
        if is_valid:
            verified_assets.append(asset_id)

    return verified_assets
