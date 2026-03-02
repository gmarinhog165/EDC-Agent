from typing import Any, Dict, List
from edc_agent.cp.contract_definition.contractBuilder import ContractDefinitionBuilder


def create_contract_definition(access_policy_id: str, contract_policy_id: str, asset_ids: List[str]) -> Dict[str, Any]:
    # Criar um ID para a definição de contrato baseado no primeiro asset_id da lista
    # ou usar um nome genérico se a lista estiver vazia
    contract_def_id = f"{asset_ids[0]}-contract-def" if asset_ids else "multi-asset-contract-def"
    
    # Usar o builder para criar a definição de contrato
    builder = ContractDefinitionBuilder(contract_def_id)
    
    builder.with_access_policy_id(access_policy_id) \
           .with_contract_policy_id(contract_policy_id) \
           .with_asset_ids(asset_ids) \
           .build()
    
    contract_definition = builder.to_json()
    
    return contract_definition