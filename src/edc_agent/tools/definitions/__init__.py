from langchain_core.tools import BaseTool

from .fetch_item_data_tool import fetch_item_data, fetch_item_data_tool
from .search_catalog_tool import search_catalog, search_catalog_tool


def get_langchain_tools() -> list[BaseTool]:
    return [search_catalog_tool, fetch_item_data_tool]


__all__ = [
    "fetch_item_data",
    "fetch_item_data_tool",
    "get_langchain_tools",
    "search_catalog",
    "search_catalog_tool",
]
