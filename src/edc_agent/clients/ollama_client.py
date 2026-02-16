import logging
import os

from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

# TODO: Add retry logic and error handling for robustness
# Classe para o Ollama
class OllamaClient:
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
        
