import json
from typing import Any, Dict

from edc_agent.cp.transfer.DataDestinationBuilder import DataDestinationBuilder


class MongoDataDestinationBuilder(DataDestinationBuilder):
    """Construtor para MongoDB DataDestination."""
    
    def __init__(self):
        super().__init__()
        self._data_destination["type"] = "MongoDB"
        self._data_destination["connectionString"] = ""
        self._data_destination["database"] = ""
        self._data_destination["collection"] = ""
        self._data_destination["filename"] = ""
    
    def with_connection_string(self, connection_string: str) -> 'MongoDataDestinationBuilder':
        """Define a string de conexão do MongoDB."""
        self._data_destination["connectionString"] = connection_string
        return self
    
    def with_database(self, database: str) -> 'MongoDataDestinationBuilder':
        """Define o nome da base de dados."""
        self._data_destination["database"] = database
        return self
    
    def with_collection(self, collection: str) -> 'MongoDataDestinationBuilder':
        """Define o nome da coleção."""
        self._data_destination["collection"] = collection
        return self
    
    def with_filename(self, filename: str) -> 'MongoDataDestinationBuilder':
        """Define o nome do ficheiro."""
        self._data_destination["filename"] = filename
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataDestination MongoDB configurado."""
        return self._data_destination