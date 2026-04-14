# Tools Sandbox

Esta pasta e independente do `Agent` e serve para desenvolver e testar tools localmente.

## Estrutura minima

- `definitions/*.py`: 1 ficheiro por tool, com `BaseModel` (args schema) e `BaseTool` (LangChain).
- `sandbox.py`: runner de linha de comandos para invocar uma tool.

Nota: as tools de `cp/lib` dependem das libs desse modulo (ex: `python-dotenv`).

## Teste rapido

```bash
python src/edc_agent/tools/sandbox.py search_catalog '{"query":"gaming mouse","expansions":["usb peripheral","high dpi mouse","esports pointer"]}'
python src/edc_agent/tools/sandbox.py fetch_item_data '{"item_id":"KBM-001"}'
```

Podes adicionar uma nova tool criando um ficheiro em `definitions/` e registando-a em `get_langchain_tools()` (`definitions/__init__.py`).

Para integração LangChain:
- Usa `list_langchain_tools()` para obter `list[BaseTool]` (entrada para `create_tool_calling_agent`).
