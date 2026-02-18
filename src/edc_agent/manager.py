import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .agents.agent import Agent

logger = logging.getLogger(__name__)

# O PipelineManager é responsável por gerir a conversa, decidir qual agente deve responder e manter o histórico de mensagens.
class PipelineManager:
    def __init__(self, router_agent: Agent, search_catalog_agent: Agent, fetch_data_agent: Agent):
        self.router_agent = router_agent
        self.search_catalog_agent = search_catalog_agent
        self.fetch_data_agent = fetch_data_agent
        self.chat_history: list[BaseMessage] = [] # BaseMessage é a classe pai de HumanMessage e AIMessage

    # Prompt inicial para ser o Agente a iniciar conversa com o user (TODO verificar se é a melhor prática assim)
    def start_conversation(self) -> tuple[str, bool]:
        logger.info("Starting conversation with search-catalog agent")
        initial_prompt = "Start the conversation with a short greeting and ask how you can help."
        response, is_done = self.search_catalog_agent.generate_response(initial_prompt, self.chat_history)
        return response, is_done

    # Resolver o agente correto com base na rota identificada pelo router agent
    def _resolve_agent(self, route: str) -> Agent:
        if route == "fetch-data":
            return self.fetch_data_agent
        return self.search_catalog_agent

    # O router pode retornar respostas variadas, então precisamos de uma função para normalizar e identificar a rota correta
    def _select_route(self, router_response: str) -> str:
        normalized = router_response.strip().lower()
        if "fetch-data" in normalized or "fetch_data" in normalized:
            return "fetch-data"
        if "search-catalog" in normalized or "search_catalog" in normalized:
            return "search-catalog"
        return "retry"

    def process(self, user_message: str) -> tuple[str, bool]:
        logger.debug("Processing user message len=%d", len(user_message))

        # Primeira mensagem para o router agent, assim ele saberá escolher o agente adequado
        router_output, _ = self.router_agent.generate_response(user_message, self.chat_history)
        logger.debug("Router output=%s", router_output.strip())

        # Resposta do router que aponta para o agente adequado
        route = self._select_route(router_output)

        # Caso não consiga identificar o Agente correto (TODO por testar)
        if route == "retry":
            logger.warning("Router could not determine route for message")
            return "Sorry, I couldn't determine the right action. Could you please rephrase?", False

        # Escolher o agente
        selected_agent = self._resolve_agent(route)
        logger.info("Routing message route=%s selected_agent=%s", route, selected_agent.name)

        # O Agente vai processar a mensagem do user
        agent_response, is_done = selected_agent.generate_response(user_message, self.chat_history)

        # Atualizar o histórico de mensagens com a mensagem do user e a resposta do agente
        self.chat_history.append(HumanMessage(content=user_message))
        self.chat_history.append(AIMessage(content=agent_response))
        logger.debug("Chat history updated size=%d is_done=%s", len(self.chat_history), is_done)
        
        # Retorna a resposta e se já acabou o processamento
        return agent_response, is_done

    def reset_history(self) -> None:
        self.chat_history.clear()
        logger.info("Chat history reset")

    # Método para debug
    def formatted_chat_history(self) -> str:
        if not self.chat_history:
            return "[empty]"

        lines: list[str] = []
        for index, message in enumerate(self.chat_history, start=1):
            role = message.type
            content = str(message.content).strip()
            lines.append(f"{index}. {role}: {content}")
        return "\n".join(lines)
