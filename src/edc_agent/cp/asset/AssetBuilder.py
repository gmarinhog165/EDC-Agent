from typing import List
import uuid
from edc_agent.cp.asset.Asset import Asset
from edc_agent.cp.asset.DataAddressBuilder import DataAddressBuilder


class AssetBuilder:
    """Construtor principal para o Asset completo."""
    
    def __init__(self):
        self._asset = Asset(asset_id=f"asset-{uuid.uuid4()}")
    
    def with_id(self, asset_id: str) -> 'AssetBuilder':
        """Define o ID do asset."""
        self._asset.asset_id = asset_id
        return self
    
    def with_context(self, context: List[str]) -> 'AssetBuilder':
        """Define o contexto do asset."""
        self._asset.context = context
        return self
    
    def with_description(self, description: str) -> 'AssetBuilder':
        """Define a descrição do asset."""
        self._asset.description = description
        return self
    
    def with_data_address(self, data_address_builder: DataAddressBuilder) -> 'AssetBuilder':
        """Define o DataAddress usando um construtor específico."""
        self._asset.data_address = data_address_builder.build()
        return self
    
    def build(self) -> Asset:
        """Constrói e retorna o Asset configurado."""
        return self._asset