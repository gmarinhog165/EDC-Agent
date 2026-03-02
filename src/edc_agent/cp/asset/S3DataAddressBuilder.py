from typing import Any, Dict
    
from edc_agent.cp.asset.DataAddressBuilder import DataAddressBuilder


class S3DataAddressBuilder(DataAddressBuilder):
    """Construtor para S3 DataAddress."""
    
    def __init__(self):
        super().__init__()
        self._data_address["type"] = "AmazonS3"
        self._data_address["region"] = ""
        self._data_address["bucketName"] = ""
        self._data_address["objectName"] = ""
        self._data_address["endpointOverride"] = ""
    
    def with_region(self, region: str) -> 'S3DataAddressBuilder':
        """Define a região do S3."""
        self._data_address["region"] = region
        return self
    
    def with_bucket_name(self, bucket_name: str) -> 'S3DataAddressBuilder':
        """Define o nome do bucket S3."""
        self._data_address["bucketName"] = bucket_name
        return self
    
    def with_object_name(self, object_name: str) -> 'S3DataAddressBuilder':
        """Define o nome do objeto S3."""
        self._data_address["objectName"] = object_name
        return self
    
    def with_endpoint_override(self, endpoint_override: str) -> 'S3DataAddressBuilder':
        """Define o endpoint customizado (ex: 'http://localhost:9000' para MinIO)."""
        self._data_address["endpointOverride"] = endpoint_override
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataAddress S3 configurado."""
        return self._data_address