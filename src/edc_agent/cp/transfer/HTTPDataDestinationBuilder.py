from typing import Dict, Any
from edc_agent.cp.transfer.DataDestinationBuilder import DataDestinationBuilder


class HTTPDataDestinationBuilder(DataDestinationBuilder):
    """Construtor para HTTP DataAddress."""
    
    def __init__(self):
        super().__init__()
        #pedido examplo no samples, transfer02
        self._data_destination["type"] = ""
        #ex baseURL: "http://localhost:4000/api/consumer/store"
        self._data_destination["baseUrl"] = ""
    
    def with_base_url(self, base_url: str) -> 'HTTPDataDestinationBuilder':
        """Define a URL base."""
        self._data_destination["baseUrl"] = base_url
        return self
    
    def with_type(self, type_value):
        """define o type"""
        self._data_destination["type"] = type_value
        return self
        
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataDestination HTTP configurado."""
        return self._data_destination
