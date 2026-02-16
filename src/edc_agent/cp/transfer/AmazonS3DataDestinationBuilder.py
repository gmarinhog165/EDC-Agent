import json
from typing import Any, Dict

from edc_agent.cp.transfer.DataDestinationBuilder import DataDestinationBuilder

class AmazonS3DataDestinationBuilder(DataDestinationBuilder):
    """Construtor para Amazon S3 DataDestination."""
    
    def __init__(self):
        super().__init__()
        self._data_destination["type"] = "AmazonS3"
        self._data_destination["region"] = ""
        self._data_destination["bucketName"] = ""
        self._data_destination["objectName"] = ""
        self._data_destination["endpointOverride"] = ""
    
    def with_region(self, region: str) -> 'AmazonS3DataDestinationBuilder':
        """Define a região do S3."""
        self._data_destination["region"] = region
        return self
    
    def with_bucket_name(self, bucket_name: str) -> 'AmazonS3DataDestinationBuilder':
        """Define o nome do bucket."""
        self._data_destination["bucketName"] = bucket_name
        return self
    
    def with_object_name(self, object_name: str) -> 'AmazonS3DataDestinationBuilder':
        """Define o nome do objeto."""
        self._data_destination["objectName"] = object_name
        return self
    
    #pode ser por ex: "http://localhost:9000" para o minio
    def with_endpoint_override(self, endpoint_override: str) -> 'AmazonS3DataDestinationBuilder':
        """Define o endpoint customizado."""
        self._data_destination["endpointOverride"] = endpoint_override
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataDestination Amazon S3 configurado."""
        return self._data_destination