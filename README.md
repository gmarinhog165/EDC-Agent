# EDC-Agent

O EDC-Agent é um assistente de linha de comandos, leve e multiagente, desenvolvido em Python.
Utiliza um LLM com Ollama e encaminha os pedidos do utilizador entre agentes especializados.

## Funcionalidades

- Pipeline multiagente com um router dedicado.
- Dois agentes de tarefa:
  - `search-catalog`: ajuda o utilizador a procurar e filtrar opções no catálogo.
  - `fetch-data`: obtém informação detalhada sobre um item selecionado.
- Suporte para histórico de conversa e limpeza de contexto.
- Modelo, temperatura e logs configuráveis via CLI.

## Requisitos

- Python `>=3.10`
- Ollama em execução local (predefinição: `http://localhost:11434`)
- Um modelo Ollama já descarregado (predefinição na CLI: `llama3.1:8b`)

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuração

Variáveis de ambiente:

- `OLLAMA_BASE_URL`: opcional. Por predefinição usa `http://localhost:11434`.

Também é suportado um ficheiro `.env` (carregado automaticamente no arranque).

## Execução

Usando o entrypoint do módulo:

```bash
python -m edc_agent
```

Ou após a instalação:

```bash
edc-agent
```

Opções da CLI:

- `--model` (predefinição: `llama3.1:8b`)
- `--temperature` (predefinição: `0`)
- `--log-level` (predefinição: `INFO`)
- `--log-file` (predefinição: desativado)

Exemplo:

```bash
python -m edc_agent --model llama3.1:8b --temperature 0 --log-level DEBUG
```

## Comandos da CLI

Durante a sessão interativa:

- `/reset`: limpa o histórico de conversa e reinicia a sessão.
- `/exit`: termina a sessão.

## Estrutura do Projeto

```text
src/edc_agent/
  main.py                  # Entrada da CLI e ligação do pipeline
  manager.py               # Encaminhamento e estado da conversa
  logging_config.py        # Configuração de logging
  agents/agent.py          # Abstração genérica de agente
  clients/ollama_client.py # Wrapper do cliente Ollama
  prompts/                 # Prompts do router e dos agentes de tarefa
```

## Como Funciona o Encaminhamento

1. A mensagem do utilizador é enviada para o agente `router`.
2. O router devolve uma rota: `search-catalog` ou `fetch-data`.
3. O agente de tarefa selecionado gera a resposta final.
4. O histórico da conversa é atualizado com as mensagens do utilizador e do assistente.

Os agentes de tarefa podem marcar conclusão com `<DONE>`, que é removido da resposta visível e exposto como sinal interno de conclusão.

## Notas

- Este projeto privilegia atualmente simplicidade de routing e iteração rápida.
- Pode ser reforçado de forma incremental com retries, validação mais rica e lógica de routing mais avançada.
