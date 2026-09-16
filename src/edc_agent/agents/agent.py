import logging
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

class LLMClient(Protocol):
    def generate_response(self, messages: list[BaseMessage]) -> str: ...
    def generate_response_with_tools(
        self, messages: list[BaseMessage], tools: list[BaseTool], tool_choice: str | None = None
    ) -> tuple[str, list[BaseMessage]]: ...


class Agent:
    def __init__(
        self,
        name: str,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[BaseTool] | None = None,
        forced_tool_choice: str | None = None,
    ):
        self.name = name
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.tools = tools or []
        self._tool_choice = forced_tool_choice
        self._done_markers = ("<DONE>",)
    
    # Retorna a resposta do agente e um booleano indicando se a conversa deve ser encerrada
    def generate_response(
        self,
        user_message: str,
        chat_history: list[BaseMessage] | None = None,
    ) -> tuple[str, bool, list[BaseMessage]]:
        history = chat_history or []

        logger.debug(
            "Agent=%s generating response user_message_len=%d chat_history=%d",
            self.name,
            len(user_message),
            len(history),
        )

        # Concat da system prompt, histórico e mensagem do usuário para enviar ao modelo
        messages = self._build_messages(user_message, history)

        # Chama o modelo para gerar a resposta, infere se a conversa deve ser encerrada e limpa os marcadores de done da resposta
        if self.tools:
            raw_response, execution_messages = self.llm_client.generate_response_with_tools(
                messages, self.tools, self._tool_choice
            )
        else:
            raw_response = self.llm_client.generate_response(messages)
            execution_messages = []

        # Verifica se a resposta contém algum marcador de done (em self._done_markers
        is_done = self._infer_is_done(raw_response)
        # Remove os marcadores de done da resposta para retornar apenas o conteúdo relevante
        clean_response = self._strip_done_markers(raw_response)
        clean_execution_messages = self._strip_done_markers_from_messages(execution_messages)

        logger.debug("Agent=%s generated response is_done=%s", self.name, is_done)
        return clean_response, is_done, clean_execution_messages
    
    # Constrói a lista de mensagens para enviar ao modelo, incluindo a system prompt, histórico e mensagem do user
    def _build_messages(self, user_message: str, chat_history: list[BaseMessage]) -> list[BaseMessage]:
        return [
            SystemMessage(content=f"Agent: {self.name}\n\n{self.system_prompt}"),
            *chat_history,
            HumanMessage(content=user_message),
        ]
    
    # Verifica se a resposta do modelo contém algum marcador de done definido em self._done_markers, indicando que a conversa deve ser encerrada
    def _infer_is_done(self, model_response: str) -> bool:
        lowered = model_response.lower()
        if any(marker.lower() in lowered for marker in self._done_markers):
            return True
        return False

    # Remove os marcadores de done da resposta do modelo, retornando apenas o conteúdo relevante para a conversa
    def _strip_done_markers(self, model_response: str) -> str:
        cleaned = model_response
        for marker in self._done_markers:
            cleaned = cleaned.replace(marker, "")
        return cleaned.strip()

    def _strip_done_markers_from_messages(
        self, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        cleaned_messages: list[BaseMessage] = []
        for message in messages:
            if isinstance(message, AIMessage) and isinstance(message.content, str):
                cleaned_messages.append(
                    message.model_copy(
                        update={"content": self._strip_done_markers(message.content)}
                    )
                )
                continue
            cleaned_messages.append(message)
        return cleaned_messages
