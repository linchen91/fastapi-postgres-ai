import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

_llm = None
_analysis_llm = None
_tavily_client = None

def load_dotenv_once():
    if _tavily_client is None and _llm is None and _analysis_llm is None:
        load_dotenv(override=True)

def _get_llm_config():
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_id = os.getenv("LLM_BASE_MODEL")
    if not api_key or not base_url or not model_id:
        raise ValueError("LLM BASE API configuration is missing.")
    return api_key, base_url, model_id

def get_llm(tp=None):
    global _llm
    if tp is None:
        tp = 0.7
    load_dotenv_once()
    if _llm is None:
        api_key, base_url, model_id = _get_llm_config()
        _llm = ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            temperature=tp,
        )
    else:
        _llm.temperature = tp
    return _llm

def get_analysis_llm():
    global _analysis_llm
    load_dotenv_once()
    if _analysis_llm is None:
        api_key, base_url, model_id = _get_llm_config()
        _analysis_llm = ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
        )
    return _analysis_llm

def get_tavily():
    global _tavily_client
    load_dotenv_once()
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily_client