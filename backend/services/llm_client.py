import os
import json
import requests

# Manual .env loader to support simple configuration without installing extra libraries
def load_env():
    possible_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        # Skip blank lines and comments
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip("'\"")
                print(f"[LLM Client] Successfully loaded environment from: {abs_path}")
                return True
            except Exception as e:
                print(f"[LLM Client] Error parsing {abs_path}: {e}")
    return False

# Initialize environment variables at import time
load_env()

def get_provider_details():
    """
    Detects which API key is present and returns the active provider.
    Priority order: Groq -> OpenAI -> Anthropic
    """
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    if groq_key:
        return "groq", groq_key
    elif openai_key:
        return "openai", openai_key
    elif anthropic_key:
        return "anthropic", anthropic_key
    return None, None

def is_ai_available() -> bool:
    provider, _ = get_provider_details()
    return provider is not None

def clean_json_response(text: str) -> str:
    """
    Cleans typical Markdown code fences (e.g. ```json ... ```) 
    that LLMs wrap their responses with to guarantee valid JSON decoding.
    """
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") or part.startswith("["):
                return part
    return text

def call_llm(prompt: str, system_prompt: str = None, max_tokens: int = 600, temperature: float = 0.7, json_response: bool = False, speed: str = "smart"):
    """
    Unified LLM caller. Standardizes prompt, parameters, model selection,
    headers, and error handling for Groq, OpenAI, and Anthropic.
    """
    provider, api_key = get_provider_details()
    if not provider:
        return None

    # Model Mappings for the providers
    models = {
        "groq": {
            "smart": "llama-3.3-70b-versatile",
            "fast": "llama-3.1-8b-instant"
        },
        "openai": {
            "smart": "gpt-4o-mini",  # Highly capable and fast
            "fast": "gpt-4o-mini"
        },
        "anthropic": {
            "smart": "claude-3-5-sonnet-20241022",
            "fast": "claude-3-haiku-20240307"
        }
    }
    
    model = models[provider].get(speed, models[provider]["smart"])
    
    try:
        if provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            if json_response:
                payload["response_format"] = {"type": "json_object"}
                
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                res_text = response.json()["choices"][0]["message"]["content"]
                return clean_json_response(res_text)
            else:
                print(f"[LLM Client] Groq API returned status {response.status_code}: {response.text}")
                
        elif provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            if json_response:
                payload["response_format"] = {"type": "json_object"}
                
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                res_text = response.json()["choices"][0]["message"]["content"]
                return clean_json_response(res_text)
            else:
                print(f"[LLM Client] OpenAI API returned status {response.status_code}: {response.text}")
                
        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            }
            if system_prompt:
                payload["system"] = system_prompt
                
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                res_text = response.json()['content'][0]['text']
                return clean_json_response(res_text)
            else:
                print(f"[LLM Client] Anthropic API returned status {response.status_code}: {response.text}")
                
    except Exception as e:
        print(f"[LLM Client] Exception during API call to {provider}: {e}")
        
    return None
