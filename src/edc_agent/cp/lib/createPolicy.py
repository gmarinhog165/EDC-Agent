from pathlib import Path
import json


def load_policy_template(template_path):

    template_path = Path(template_path)
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template não encontrado: {template_path}")
    
    with open(template_path, 'r') as file:
        template_content = file.read()
    
    # Validar se é um JSON válido
    try:
        json.loads(template_content)
    except json.JSONDecodeError:
        raise ValueError(f"O arquivo {template_path} não contém um JSON válido")
        
    return template_content


def get_available_templates(templates_dir):

    templates_dir = Path(templates_dir)
    
    if not templates_dir.exists() or not templates_dir.is_dir():
        raise NotADirectoryError(f"Diretório de templates não encontrado: {templates_dir}")
    
    templates = list(templates_dir.glob("*.json"))
    return templates