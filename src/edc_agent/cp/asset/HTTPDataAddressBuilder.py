from typing import Dict, Any
from edc_agent.cp.asset.DataAddressBuilder import DataAddressBuilder


class HTTPDataAddressBuilder(DataAddressBuilder):
    """Construtor para HTTP DataAddress."""
    
    def __init__(self):
        super().__init__()
        self._data_address["type"] = "HttpData"
        self._data_address["baseUrl"] = ""
        self._data_address["proxyPath"] = "true"
        self._data_address["proxyQueryParams"] = "true"
    
    def with_base_url(self, base_url: str) -> 'HTTPDataAddressBuilder':
        """Define a URL base."""
        self._data_address["baseUrl"] = base_url
        return self
    
    def with_proxy_path(self, proxy_path: bool) -> 'HTTPDataAddressBuilder':
        """Define se deve usar proxy path."""
        self._data_address["proxyPath"] = str(proxy_path).lower()
        return self
    
    def with_proxy_query_params(self, proxy_params: bool) -> 'HTTPDataAddressBuilder':
        """Define se deve usar proxy para parâmetros de consulta."""
        self._data_address["proxyQueryParams"] = str(proxy_params).lower()
        return self
    
    def with_auth(self, auth_key: str, auth_code: str) -> 'HttpDataAddressBuilder':
        """Define autenticação para o HttpData.
        
        Args:
            auth_key: Nome do header de autenticação (ex: "Authorization")
            auth_code: Valor do header de autenticação (ex: "Bearer token123")
        """
        self._data_address["authKey"] = auth_key
        self._data_address["authCode"] = auth_code
        return self
    
    def with_bearer_token(self, token: str) -> 'HttpDataAddressBuilder':
        """Método de conveniência para autenticação Bearer.
        
        Args:
            token: O token de autenticação
        """
        return self.with_auth("Authorization", f"Bearer {token}")
    
    def with_method(self, method: str) -> 'HttpDataAddressBuilder':
        """Define o método HTTP (GET, POST, PUT, etc.)."""
        self._data_address["method"] = method.upper()
        return self
    
    def with_json_body(self, json_data: dict) -> 'HttpDataAddressBuilder':
        """Método de conveniência para definir body JSON."""
        import json
        self._data_address["body"] = json.dumps(json_data, separators=(',', ':'))
        self._data_address["contentType"] = "application/json"
        return self
    
    def with_content_type(self, content_type: str) -> 'HttpDataAddressBuilder':
        """Define o Content-Type do request."""
        self._data_address["contentType"] = content_type
        return self
    
    def with_proxy_body(self, proxy_body: bool) -> 'HttpDataAddressBuilder':
        """Define se o corpo do request deve ser enviado via proxy."""
        self._data_address["proxyBody"] = str(proxy_body).lower()
        return self
    
    def build(self) -> Dict[str, Any]:
        """Constrói e retorna o DataAddress HTTP configurado."""
        return self._data_address
