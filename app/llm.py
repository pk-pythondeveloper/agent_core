from openai import AsyncOpenAI
from app.config import settings


def _create_chat_client():
    provider = settings.llm_provider.strip().lower()
    if provider == "groq":
        if not settings.groq_api_key:
            return None
        return AsyncOpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    if provider == "openai":
        if not settings.openai_api_key:
            return None
        return AsyncOpenAI(api_key=settings.openai_api_key)
    raise ValueError("LLM_PROVIDER must be 'openai' or 'groq'")


chat_client = _create_chat_client()
embedding_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
chat_model = settings.groq_model if settings.llm_provider.strip().lower() == "groq" else settings.openai_model
