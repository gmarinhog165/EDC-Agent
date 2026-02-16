from typing import List
import uuid
from edc_agent.cp.negotiation.Negotiation import Negotiation


class NegotiationBuilder:
    """Construtor para Negotion."""
    
    def __init__(self):
        self._negotiation = Negotiation()

    def with_policy_id(self,policy_id:str) -> 'NegotiationBuilder':
        """Define o id da politica"""
        self._negotiation.policyID=policy_id
        return self

    def with_asset_id(self, asset_id: str) -> 'NegotiationBuilder':
        """Define o ID do asset."""
        self._negotiation.asset_id = asset_id
        return self
    
    def build(self) -> Negotiation:
        """Constrói e retorna a negociacao configurado."""
        return self._negotiation