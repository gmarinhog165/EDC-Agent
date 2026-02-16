from abc import ABC, abstractmethod
from typing import Any, Dict

class DataDestinationBuilder(ABC):
    """Construtor abstrato de DataDestination."""
    
    def __init__(self):
        self._data_destination = {"type": ""}
    
    @abstractmethod
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataDestination."""
        pass
    
    def with_type(self, type_value: str) -> 'DataDestinationBuilder':
        """Define o tipo do DataDestination."""
        self._data_destination["type"] = type_value
        return self