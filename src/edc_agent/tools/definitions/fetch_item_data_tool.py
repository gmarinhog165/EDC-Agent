from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class FetchItemDataArgs(BaseModel):
    item_id: str = Field(description="Asset ID selected for data exchange.")


class FetchItemDataTool(BaseTool):
    name: str = "fetch_item_data"
    description: str = "Fetch data exchange details for a specific asset ID."
    args_schema: type[BaseModel] = FetchItemDataArgs

    def _run(self, item_id: str) -> None:
        return fetch_item_data(item_id=item_id)


fetch_item_data_tool = FetchItemDataTool()

def fetch_item_data(item_id: str) -> None:
    """Compatibility helper for direct calls outside LangChain tool execution."""
    return None
