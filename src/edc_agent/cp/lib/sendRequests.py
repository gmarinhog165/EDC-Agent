import os
from typing import Any, Dict

import requests
from edc_agent.cp.env_loader import load_cp_env
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_cp_env()
API_KEY = os.getenv("API_KEY", "password")

def send_post_request(path, endpoint, body) -> Dict[str, Any]:
    """Envia um request POST com o JSON do asset."""
    
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": API_KEY,
    }

    url = f"{path}{endpoint}"
    
    try:
        response = requests.post(url, headers=headers, data=body)
        response.raise_for_status()
        print(f"POST request enviado para {url} com sucesso.\n")
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar request: {e}")
        return None

    
def send_get_request(path: str, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": API_KEY
    }

    url = f"{path}{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        print(f"GET request enviado para {url} com sucesso.\n")
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar request: {e}")
        return None
    
def send_get_request_auth(path: str, endpoint: str, auth: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    headers = {
        "Authorization": auth,
        "X-Api-Key": API_KEY
    }
    # Removido o Content-Type para requests GET

    url = f"{path}{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params, verify=False)
        response.raise_for_status()
        print(f"GET request enviado para {url} com sucesso.\n")
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar request: {e}")
        # Adicionar mais informação de debug
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status Code: {e.response.status_code}")
            print(f"Response Text: {e.response.text}")
        return None