# EDC-Agent

O EDC-Agent é um assistente CLI multiagente desenvolvido em Python.
Corre totalmente com modelos locais no Ollama e encaminha pedidos do utilizador entre agentes especializados.

## Funcionalidades

- Pipeline multiagente com agente `router` dedicado.
- Agentes de tarefa:
  - `search-catalog` (usa a tool `search_catalog`)
  - `fetch-data` (usa a tool `fetch_item_data`)
- Fluxo de tool-calling com geração de resposta final:
  - primeira chamada ao modelo decide as tool calls
  - as tools são executadas
  - segunda chamada ao modelo produz a resposta final em linguagem natural
- Gestão de histórico com `/reset`.
- Marcadores `<DONE>` são removidos das respostas visíveis e também limpos nas `execution_messages` antes de irem para o histórico.

## Requisitos

- Python `>=3.10`
- Ollama em execução local (predefinição: `http://localhost:11434`)
- Modelos Ollama descarregados localmente:
  - modelo de chat, por exemplo `qwen3:8b`
  - modelo de embeddings, por exemplo `qwen3-embedding:0.6b`

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuração

Variáveis de ambiente (podem ser definidas no `.env`):

- `LLM_MODEL`: nome do modelo de chat usado como default da CLI.
- `OLLAMA_BASE_URL`: URL base do Ollama (predefinição: `http://localhost:11434`).
- `EMBEDDING_MODEL`: modelo de embeddings usado por `search_catalog`.
  - deve estar no formato Ollama `name:tag`
  - exemplo: `qwen3-embedding:0.6b`

Exemplo de `.env`:

```env
LLM_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=qwen3-embedding:0.6b
```

## Execução

```bash
python -m edc_agent
```

Opções da CLI:

- `--model` (predefinição: valor de `LLM_MODEL`)
- `--temperature` (predefinição: `0`)
- `--log-level` (predefinição: `INFO`)
- `--log-file` (predefinição: desativado)

Exemplo:

```bash
python -m edc_agent --model qwen3:8b --temperature 0 --log-level DEBUG
```

## Comandos da CLI

- `/reset`: limpa o histórico e inicia uma sessão nova.
- `/exit`, `exit`, `quit`: termina a CLI.

## Pesquisa Semântica (`search_catalog`)

A filtragem semântica do `search_catalog` é apenas com Ollama:

- os embeddings são gerados via `POST /api/embed`
- as keywords da query são enviadas com prefixo `query: `
- as descrições dos documentos são embeddadas como estão
- a similaridade de cosseno é calculada no processo
- assets com score `> 0.5` são mantidos antes dos filtros de dataplane/policy

## Estrutura do Projeto

```text
src/edc_agent/
  main.py                           # Entry point da CLI e ligação do pipeline
  manager.py                        # Seleção de rota e estado da conversa
  agents/agent.py                   # Abstração de agente e limpeza de <DONE>
  clients/ollama_client.py          # Cliente de chat Ollama + ciclo de execução de tools
  tools/definitions/search_catalog_tool.py
  tools/definitions/fetch_item_data_tool.py
  prompts/                          # Prompts do router e dos agentes de tarefa
```
