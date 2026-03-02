import json
from edc_agent.cp.asset.AssetBuilder import AssetBuilder
from edc_agent.cp.asset.HTTPDataAddressBuilder import HTTPDataAddressBuilder
from edc_agent.cp.asset.MongoDataAddressBuilder import MongoDataAddressBuilder
from edc_agent.cp.asset.AzureDataAddressBuilder import AzureDataAddressBuilder
from edc_agent.cp.asset.S3DataAddressBuilder import S3DataAddressBuilder


def lib_create_http_asset(asset_id, description, base_url, token, method, proxy_path=True, proxy_query=True) -> AssetBuilder:
    builder = AssetBuilder()
    if asset_id:
        builder.with_id(asset_id)
    if description:
        builder.with_description(description)
    
    http_builder = HTTPDataAddressBuilder() \
        .with_base_url(base_url) \
        .with_proxy_path(proxy_path) \
        .with_proxy_query_params(proxy_query) \
        .with_bearer_token(token) \
        .with_method(method) \
        .with_content_type("application/json") \
        .with_proxy_body(True)
    
    asset = builder.with_data_address(http_builder).build()
    return asset


def lib_create_mongo_asset(asset_id, description, connection_string, database, 
                      collection, query) -> AssetBuilder:
    
    builder = AssetBuilder()
    if asset_id:
        builder.with_id(asset_id)
    if description:
        builder.with_description(description)
    
    mongo_builder = MongoDataAddressBuilder() \
        .with_connection_string(connection_string) \
        .with_database(database) \
        .with_collection(collection)
    
    if query:
        try:
            query_dict = json.loads(query) if isinstance(query, str) else query
            mongo_builder.with_query(query_dict)
        except json.JSONDecodeError:
            raise ValueError("Formato de query inválido.")
    
    asset = builder.with_data_address(mongo_builder).build()
    return asset


def lib_create_azure_asset(asset_id, description, account_name, container_name, 
                      blob_name) -> AssetBuilder:
    
    builder = AssetBuilder()
    if asset_id:
        builder.with_id(asset_id)
    if description:
        builder.with_description(description)
    
    azure_builder = AzureDataAddressBuilder() \
        .with_account_name(account_name) \
        .with_container_name(container_name)
    
    if blob_name:
        azure_builder.with_blob_name(blob_name)

    
    asset = builder.with_data_address(azure_builder).build()
    return asset


def lib_create_s3_asset(asset_id: str, description: str, region: str, bucket_name: str, object_name: str, endpoint_override: str = "") -> AssetBuilder:
    """Cria um AssetBuilder com S3 DataAddress."""
    builder = AssetBuilder()
    if asset_id:
        builder.with_id(asset_id)
    if description:
        builder.with_description(description)
    
    s3_builder = S3DataAddressBuilder() \
        .with_region(region) \
        .with_bucket_name(bucket_name) \
        .with_object_name(object_name)
    
    # Adicionar endpoint override apenas se fornecido
    if endpoint_override:
        s3_builder.with_endpoint_override(endpoint_override)
    
    asset = builder.with_data_address(s3_builder).build()
    return asset