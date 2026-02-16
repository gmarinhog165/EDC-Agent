from abc import ABC, abstractmethod
from typing import Any, Dict

class DataAddressBuilder(ABC):
    """Construtor abstrato de DataAddress."""
    
    def __init__(self):
        self._data_address = {"@type": "DataAddress"}
    
    @abstractmethod
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataAddress."""
        pass
    
    def with_type(self, type_value: str) -> 'DataAddressBuilder':
        """Define o tipo do DataAddress."""
        self._data_address["type"] = type_value
        return self