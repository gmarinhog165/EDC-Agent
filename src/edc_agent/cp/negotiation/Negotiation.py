from dataclasses import dataclass, field
from typing import Dict, List, Any
import json
import os
from edc_agent.cp.env_loader import load_cp_env

# Carregar variáveis do arquivo .env
load_cp_env()

@dataclass
class Negotiation:
    """Classe que representa um pedido de Negotiation conforme a especificação."""
    # Fields without default values or with field(default=...) first
    permission: list = field(default_factory=list)
    prohibition: list = field(default_factory=list)
    policyID: str = ""
    asset_id: str = ""
    
    # Fields with default values
    context: List[str] = field(default_factory=lambda: ["https://w3id.org/edc/connector/management/v0.0.1"])
    type: str = "ContractRequest"
    counter_party_address: str = field(default_factory=lambda: f"{os.getenv('PROVIDER_DSP_URL', '')}/api/dsp")
    counter_party_id: str = field(default_factory=lambda: os.getenv("PROVIDER_ID", ""))
    protocol: str = "dataspace-protocol-http"
    left_operand: str = "DataAccess.level"
    operator: str = "eq"
    right_operand: str = "processing"

    def to_json(self) -> str:
        """Converte o pedido de negotiation para formato JSON."""
        asset_transfer_dict = {
            "@context": self.context,
            "@type": self.type,
            "counterPartyAddress": self.counter_party_address,
            "counterPartyId": self.counter_party_id,
            "protocol": self.protocol,
            "policy":{
                "@type": "Offer",
                "@id": self.policyID,
                "assigner":self.counter_party_id,
                "permission":self.permission,
                "prohibition": self.prohibition,
                "obligation":{
                    "action": "use",
                    "constraint":{
                        "leftOperand":self.left_operand,
                        "operator":self.operator,
                        "rightOperand":self.right_operand
                    }
                },
                "target": self.asset_id
            },
            "callbackAddresses":[]
        }
        return json.dumps(asset_transfer_dict, indent=4)

    def to_dict(self) -> Dict[str, Any]:
        """Converte o pedido de negotiation para um dicionário."""
        return {
            "@context": self.context,
            "@type": self.type,
            "counterPartyAddress": self.counter_party_address,
            "counterPartyId": self.counter_party_id,
            "protocol": self.protocol,
            "policy":{
                "@type": "offer",
                "@id": self.policyID,
                "assigner":self.counter_party_id,
                "permission":self.permission,
                "prohibition": self.prohibition,
                "obligation":{
                    "action": "use",
                    "constraint":{
                        "leftOperand":self.left_operand,
                        "operator":self.operator,
                        "rightOperand":self.right_operand
                    }
                },
                "target": self.asset_id
            },
            "callbackAddresses":[]
        }