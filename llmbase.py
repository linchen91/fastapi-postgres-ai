import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

_llm = None
_tavily_client = None

def _get_openrouter_config():
    if _tavily_client is None:
        load_dotenv(override=True)
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    model_id = os.getenv("OPENROUTER_MODEL")
    if not api_key or not base_url or not model_id:
        raise ValueError("OpenRouter API configuration is missing.")
    return api_key, base_url, model_id


def get_llm(tp):
    global _llm
    if _llm is None:
        api_key, base_url, model_id = _get_openrouter_config()
        _llm = ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            temperature=tp,
        )
    else:
        _llm.temperature = tp
    return _llm

def get_tavily():
    global _tavily_client
    if _tavily_client is None:
        if _llm is None:
            load_dotenv(override=True)
        _tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily_client