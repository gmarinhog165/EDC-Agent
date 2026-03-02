import json
from typing import Any, Dict

from edc_agent.cp.asset.DataAddressBuilder import DataAddressBuilder


class MongoDataAddressBuilder(DataAddressBuilder):
    """Construtor para MongoDB DataAddress."""
    
    def __init__(self):
        super().__init__()
        self._data_address["type"] = "MongoDB"
        self._data_address["connectionString"] = ""
        self._data_address["database"] = ""
        self._data_address["filename"] = ""
        self._data_address["collection"] = ""
    
    def with_connection_string(self, connection_string: str) -> 'MongoDataAddressBuilder':
        """Define a string de conexão do MongoDB."""
        self._data_address["connectionString"] = connection_string
        return self
    
    def with_database(self, database: str) -> 'MongoDataAddressBuilder':
        """Define o nome do banco de dados."""
        self._data_address["database"] = database
        return self
    
    def with_collection(self, collection: str) -> 'MongoDataAddressBuilder':
        """Define o nome da coleção."""
        self._data_address["collection"] = collection
        return self
    
    def with_filename(self, filename: str) -> 'MongoDataAddressBuilder':
        """Define o nome do ficheiro."""
        self._data_address["filename"] = filename
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataAddress MongoDB configurado."""
        return self._data_address