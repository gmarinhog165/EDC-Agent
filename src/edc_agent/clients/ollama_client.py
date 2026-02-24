import logging
import os
import json

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from ..agents.agent import LLMClient

logger = logging.getLogger(__name__)

# TODO: Add retry logic and error handling for robustness
# Classe para o Ollama
class OllamaClient(LLMClient):
    def __init__(
            self,
            model_name: str,
            temperature: int,
            base_url: str | None = None,
    ):
        self.model_name = model_name # O nome do modelo a ser usado
        self.temperature = temperature # O nível de aleatoriedade na geração de respostas
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") # API exposta do modelo
        self.client = ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=self.base_url,
        )

        logger.info("Initialized OllamaClient model=%s base_url=%s temperature=%s", self.model_name, self.base_url, self.temperature,)

    # Gerar resposta a partir de uma lista de mensagens que contém o histórico da conversa, system prompt e query do user
    def generate_response(self, messages: list[BaseMessage]) -> str:
        logger.debug("Invoking model=%s with %d messages", self.model_name, len(messages))
        response = self.client.invoke(messages)
        logger.debug("Model=%s returned response", self.model_name)
        return response.content

    def generate_response_with_tools(
        self,
        messages: list[BaseMessage],
        tools: list[BaseTool]
    ) -> tuple[str, list[BaseMessage]]:
        if not tools:
            return self.generate_response(messages), []

        tool_model = self.client.bind_tools(tools)
        tool_map = {tool.name: tool for tool in tools}
        running_messages: list[BaseMessage] = list(messages)
        generated_messages: list[BaseMessage] = []
        last_text_response = ""

        ai_response: AIMessage = tool_model.invoke(running_messages)
        running_messages.append(ai_response)
        generated_messages.append(ai_response)
        last_text_response = str(ai_response.content or "").strip()

        tool_call = ai_response.tool_calls[0] or None

        if not tool_call:
            return last_text_response, generated_messages

        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})
        tool_call_id = tool_call.get("id", tool_name)
        selected_tool = tool_map.get(tool_name)

        if selected_tool is None:
            tool_output = {"error": f"Tool '{tool_name}' is not available."}
        else:
            try:
                args = tool_args if isinstance(tool_args, dict) else {}
                tool_output = selected_tool.invoke(args)
            except Exception as exc:  # pragma: no cover
                tool_output = {"error": f"Tool '{tool_name}' failed: {exc}"}

        tool_message = ToolMessage(
            content=self._serialize_tool_output(tool_output),
            tool_call_id=tool_call_id,
        )
        running_messages.append(tool_message)
        generated_messages.append(tool_message)

        return last_text_response, generated_messages

    def _serialize_tool_output(self, tool_output: object) -> str:
        if isinstance(tool_output, str):
            return tool_output
        return json.dumps(tool_output, ensure_ascii=True, default=str)
