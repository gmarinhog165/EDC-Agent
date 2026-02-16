from typing import List
import uuid
from edc_agent.cp.asset.CatalogAsset import CatalogAsset
from edc_agent.cp.asset.DataAddressBuilder import DataAddressBuilder


class CatalogAssetBuilder:
    """Construtor principal para o CatalogAsset completo."""
    
    def __init__(self):
        self._asset = CatalogAsset(asset_id=f"catalog-asset-{uuid.uuid4()}")
    
    def with_id(self, asset_id: str) -> 'CatalogAssetBuilder':
        """Define o ID do asset."""
        self._asset.asset_id = asset_id
        return self
    
    def with_context(self, context: List[str]) -> 'CatalogAssetBuilder':
        """Define o contexto do asset."""
        self._asset.context = context
        return self
    
    def with_description(self, description: str) -> 'CatalogAssetBuilder':
        """Define a descrição do asset."""
        self._asset.description = description
        return self
    
    def with_data_address(self, data_address_builder: DataAddressBuilder) -> 'CatalogAssetBuilder':
        """Define o DataAddress usando um construtor específico."""
        self._asset.data_address = data_address_builder.build()
        return self
    
    def build(self) -> CatalogAsset:
        """Constrói e retorna o CatalogAsset configurado."""
        return self._asset