from importlib import import_module


def _module_prefix_for_model(model_name: str) -> str:
    normalized = (model_name or "").strip().lower()
    if normalized.startswith("qwen2.5"):
        return "qwen2_5"
    if normalized.startswith("qwen3"):
        return "qwen3"
    raise ValueError(
        f"Unsupported model '{model_name}'. Configure prompts for this model under src/edc_agent/prompts/<model>/."
    )


def get_prompt(agent_name: str, model_name: str) -> str:
    module_prefix = _module_prefix_for_model(model_name)
    module_name_by_agent = {
        "router": "router_prompt",
        "search-catalog": "search_catalog_prompt",
        "fetch-data": "fetch_data_prompt",
    }
    constant_by_agent = {
        "router": "ROUTER_PROMPT",
        "search-catalog": "SEARCH_CATALOG_PROMPT",
        "fetch-data": "FETCH_DATA_PROMPT",
    }

    prompt_module_name = module_name_by_agent.get(agent_name)
    prompt_constant_name = constant_by_agent.get(agent_name)
    if not prompt_module_name or not prompt_constant_name:
        raise ValueError(f"Unsupported agent '{agent_name}'.")

    prompt_module = import_module(f".{module_prefix}.{prompt_module_name}", package=__package__)
    prompt_value = getattr(prompt_module, prompt_constant_name, None)
    if not isinstance(prompt_value, str):
        raise ValueError(
            f"Prompt constant '{prompt_constant_name}' is missing in module '{module_prefix}.{prompt_module_name}'."
        )

    return prompt_value.strip()
