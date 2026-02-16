import argparse
import logging
from dotenv import load_dotenv

from .agents.agent import Agent
from .clients.ollama_client import OllamaClient
from .logging_config import setup_logging
from .manager import PipelineManager
from .prompts.fetch_data_prompt import FETCH_DATA_PROMPT
from .prompts.router_prompt import ROUTER_PROMPT
from .prompts.search_catalog_prompt import SEARCH_CATALOG_PROMPT

logger = logging.getLogger(__name__)


def build_manager(model_name: str, temperature: int) -> PipelineManager:
    llm_client = OllamaClient(model_name=model_name, temperature=temperature)
    router_agent = Agent(name="router", llm_client=llm_client, system_prompt=ROUTER_PROMPT.strip())
    search_catalog_agent = Agent(
        name="search-catalog",
        llm_client=llm_client,
        system_prompt=SEARCH_CATALOG_PROMPT.strip(),
    )
    fetch_data_agent = Agent(
        name="fetch-data",
        llm_client=llm_client,
        system_prompt=FETCH_DATA_PROMPT.strip(),
    )
    return PipelineManager(
        router_agent=router_agent,
        search_catalog_agent=search_catalog_agent,
        fetch_data_agent=fetch_data_agent,
    )


def run_cli(model_name: str, temperature: int) -> None:
    logger.info("Starting CLI model=%s temperature=%s", model_name, temperature)
    manager = build_manager(model_name=model_name, temperature=temperature)

    print("EDC Agent pronto. Escreve a tua mensagem.")
    print("Comandos: /reset para limpar contexto, /exit para sair.")
    initial_response, initial_done = manager.start_conversation()
    print(f"\nAgente: {initial_response}")
    if initial_done:
        print("Tarefa marcada como concluída pelo agente.")
    print("\nChat history:")
    print(manager.formatted_chat_history())

    while True:
        try:
            user_message = input("\nTu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nA terminar.")
            break

        if not user_message:
            logger.debug("Ignored empty user input")
            continue
        if user_message.lower() in {"/exit", "exit", "quit"}:
            logger.info("Exit command received")
            print("A terminar.")
            break
        if user_message.lower() == "/reset":
            manager.reset_history()
            print("Histórico limpo.")
            initial_response, initial_done = manager.start_conversation()
            print(f"\nAgente: {initial_response}")
            if initial_done:
                print("Tarefa marcada como concluída pelo agente.")
            print("\nChat history:")
            print(manager.formatted_chat_history())
            continue

        try:
            response, is_done = manager.process(user_message)
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to process user message")
            print(f"Erro ao processar pedido: {exc}")
            continue

        print(f"\nAgente: {response}")
        if is_done:
            print("Tarefa marcada como concluída pelo agente.")
        print("\nChat history:")
        print(manager.formatted_chat_history())

# Main de teste
def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the EDC Agent CLI.")
    parser.add_argument("--model", default="llama3.1:8b", help="Ollama model name.")
    parser.add_argument("--temperature", type=int, default=0, help="Model temperature.") # temperatura serve para controlar a aleatoriedade das respostas do modelo. Valores mais baixos (ex: 0) tornam as respostas mais determinísticas, enquanto valores mais altos (ex: 1) aumentam a criatividade e variedade das respostas.
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR).")
    parser.add_argument("--log-file", default=None, help="Optional log file path.")
    args = parser.parse_args()
    setup_logging(level=args.log_level, log_file=args.log_file)
    logger.info("Logging configured level=%s log_file=%s", args.log_level, args.log_file)

    run_cli(model_name=args.model, temperature=args.temperature)


if __name__ == "__main__":
    main()
