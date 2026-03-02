from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import json

@dataclass
class Asset:
    """Classe que representa um Asset conforme a especificação."""
    asset_id: str = ""
    context: List[str] = field(default_factory=lambda: ["https://w3id.org/edc/connector/management/v0.0.1"])
    description: str = "This is a conventional asset."
    data_address: Dict[str, Any] = field(default_factory=dict)

    @property
    def get_asset_id(self) -> str:
        """Retorna o ID do asset."""
        return self.asset_id

    def to_json(self) -> str:
        """Converte o asset para formato JSON."""
        asset_dict = {
            "@context": self.context,
            "@id": self.asset_id,
            "@type": "Asset",
            "properties": {
                "description": self.description
            },
            "dataAddress": self.data_address
        }
        return json.dumps(asset_dict, indent=4)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte o asset para um dicionário."""
        return {
            "@context": self.context,
            "@id": self.asset_id,
            "@type": "Asset",
            "properties": {
                "description": self.description
            },
            "dataAddress": self.data_address
        }