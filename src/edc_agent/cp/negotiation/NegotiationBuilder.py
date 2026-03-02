from typing import Any, Dict
from edc_agent.cp.negotiation.Negotiation import Negotiation


class NegotiationBuilder:
    """Construtor para Negotiation."""
    
    def __init__(self):
        self._negotiation = Negotiation()

    def with_policy(self, policy: Dict[str, Any]) -> "NegotiationBuilder":
        """Define a policy integral recebida do catálogo."""
        self._negotiation.policy = policy
        return self

    def with_counter_party_address(self, address: str) -> "NegotiationBuilder":
        """Define o endereço DSP da contraparte."""
        self._negotiation.counter_party_address = address
        return self

    def with_counter_party_id(self, counter_party_id: str) -> "NegotiationBuilder":
        """Define o ID da contraparte."""
        self._negotiation.counter_party_id = counter_party_id
        return self

    def with_asset_id(self, asset_id: str) -> "NegotiationBuilder":
        """Define o ID do asset alvo da negociação."""
        self._negotiation.asset_id = asset_id
        return self
    
    def build(self) -> Negotiation:
        """Constrói e retorna a negociacao configurado."""
        return self._negotiation
