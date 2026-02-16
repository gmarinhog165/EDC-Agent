from typing import Any, Dict
    
from edc_agent.cp.transfer.DataDestinationBuilder import DataDestinationBuilder


class AzureDataDestinationBuilder(DataDestinationBuilder):
    """Construtor para Azure DataDestination."""
    
    def __init__(self):
        super().__init__()
        self._data_destination["type"] = "AzureStorage"
        self._data_destination["account"] = ""
        self._data_destination["container"] = ""
        self._data_destination["blobName"] = ""
    
    def with_account_name(self, account_name: str) -> 'AzureDataDestinationBuilder':
        """Define o nome da conta Azure Storage."""
        self._data_destination["account"] = account_name
        return self
    
    def with_container_name(self, container_name: str) -> 'AzureDataDestinationBuilder':
        """Define o nome do container Azure Storage."""
        self._data_destination["container"] = container_name
        return self
    
    def with_blob_name(self, blob_name: str) -> 'AzureDataDestinationBuilder':
        """Define o nome do blob Azure Storage."""
        self._data_destination["blobName"] = blob_name
        return self
    
    def with_key_name(self, key_name: str) -> 'AzureDataDestinationBuilder':
        """Define o nome da chave do objeto no S3."""
        self._data_destination["keyName"] = key_name
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataAddress S3 configurado."""
        return self._data_destination