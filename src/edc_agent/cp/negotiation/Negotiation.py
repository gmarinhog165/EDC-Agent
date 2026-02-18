from dataclasses import dataclass, field
import json
from typing import Any, Dict, List


@dataclass
class Negotiation:
    """Representa um ContractRequest para negociação."""

    context: List[str] = field(
        default_factory=lambda: ["https://w3id.org/edc/connector/management/v0.0.1"]
    )
    type: str = "ContractRequest"
    counter_party_address: str = ""
    counter_party_id: str = ""
    protocol: str = "dataspace-protocol-http"
    asset_id: str = ""
    policy: Dict[str, Any] = field(default_factory=dict)
    callback_addresses: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte o pedido de negotiation para um dicionário."""
        policy_payload = dict(self.policy)
        if policy_payload:
            policy_payload["assigner"] = self.counter_party_id
            policy_payload["target"] = self.asset_id

        return {
            "@context": self.context,
            "@type": self.type,
            "counterPartyAddress": self.counter_party_address,
            "counterPartyId": self.counter_party_id,
            "protocol": self.protocol,
            "policy": policy_payload,
            "callbackAddresses": self.callback_addresses,
        }

    def to_json(self) -> str:
        """Converte o pedido de negotiation para formato JSON."""
        return json.dumps(self.to_dict(), indent=4)
