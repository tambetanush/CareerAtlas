from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
import os
from dotenv import load_dotenv

load_dotenv()

def _get_google_api_keys() -> list[str]:
    keys = []
    main_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if main_key:
        keys.append(main_key)
    for i in range(1, 5):
        k = os.getenv(f"GOOGLE_API_KEY_{i}", "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = os.getenv("ENVIRONMENT", "development")
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8080")
    
    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "https://placeholder.supabase.co")
    # New-style keys (preferred): sb_publishable_* / sb_secret_*
    # Old-style fallback: anon JWT / service_role JWT (SUPABASE_SERVICE_KEY)
    supabase_publishable_key: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    supabase_secret_key: str = os.getenv("SUPABASE_SECRET_KEY", os.getenv("SUPABASE_SERVICE_KEY", ""))
    # Kept for back-compat with code that still reads the old name.
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_SECRET_KEY", ""))
    supabase_jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "")
    supabase_jwt_public_key: str = os.getenv("SUPABASE_JWT_PUBLIC_KEY", "")
    
    # LLMs
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_api_keys: list[str] = _get_google_api_keys()
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    huggingface_api_key: str = os.getenv("HUGGINGFACE_API_KEY", "")

    # Provider switch (see app/utils/llm_factory.py). One of:
    # anthropic | gemini | groq | openai_compatible
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # Ollama: http://localhost:11434/v1, LM Studio: http://localhost:1234/v1
    openai_compatible_base_url: str = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "")
    openai_compatible_api_key: str = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
    openai_compatible_model: str = os.getenv("OPENAI_COMPATIBLE_MODEL", "llama3.1")
    # Users may point the app at their own model server. On a hosted deploy that URL
    # must not reach the server's private network (SSRF), so private hosts are only
    # allowed when this is true (self-hosting).
    allow_private_llm_urls: bool = os.getenv(
        "ALLOW_PRIVATE_LLM_URLS",
        "true" if os.getenv("ENVIRONMENT", "development").lower() in ("development", "dev", "local") else "false",
    ).lower() == "true"
    
    # OpenRouter
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")

    # Tools
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # Monitoring
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")

    # Jina & Pinecone (Gap Analysis)
    jina_api_key: str = os.getenv("JINA_API_KEY", "")
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_index_name: str = os.getenv("PINECONE_INDEX_NAME", "careeratlas")
    pinecone_region: str = os.getenv("PINECONE_REGION", "us-east-1")
    pinecone_host: str = os.getenv("PINECONE_HOST", "")

    # Dev convenience: allows backend routes to run without bearer token.
    dev_bypass_auth: bool = os.getenv("DEV_BYPASS_AUTH", "false").lower() == "true"
    dev_user_id: str = os.getenv("DEV_USER_ID", "")

    # GitHub OAuth
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "")

settings = Settings()
