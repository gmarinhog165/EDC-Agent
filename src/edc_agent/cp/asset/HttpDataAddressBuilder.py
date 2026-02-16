from edc_agent.cp.asset.DataAddressBuilder import DataAddressBuilder
from typing import Dict, Any


class HttpDataAddressBuilder(DataAddressBuilder):
    """Construtor para DataAddress do tipo HttpData."""
    
    def __init__(self):
        super().__init__()
        self.with_type("HttpData")
    
    def with_base_url(self, base_url: str) -> 'HttpDataAddressBuilder':
        """Define a URL base para o HttpData."""
        self._data_address["baseUrl"] = base_url
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataAddress."""
        return self._data_address