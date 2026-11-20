"""One place that decides which chat model an agent talks to.

Providers: anthropic (Claude), gemini, groq, openai_compatible (Ollama, LM Studio,
vLLM, OpenRouter — anything that speaks the OpenAI chat API).

- The server default comes from LLM_PROVIDER in .env and falls back to the other
  providers the server has keys for (one Gemini model per key, so key rotation
  still happens on failure).
- A user can override the provider per request (see app.dependencies.llm). An
  override never falls back to another provider: a user who picked a local
  model must not have their data silently sent to a cloud one.
- Retries are left to each provider SDK (max_retries=2), which only retries
  429 / 5xx / connection errors — never 400/401/404.
"""
import logging
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

PROVIDERS = ("anthropic", "gemini", "groq", "openai_compatible")
_TIMEOUT = 60.0
_SDK_RETRIES = 2

# Set per request by app.dependencies.llm.llm_context; None means "server default".
llm_override: ContextVar[dict | None] = ContextVar("llm_override", default=None)


def available_providers() -> list[str]:
    """Providers the server itself has credentials/endpoints for."""
    have = {
        "anthropic": bool(settings.anthropic_api_key),
        "gemini": bool(settings.google_api_keys),
        "groq": bool(settings.groq_api_key),
        "openai_compatible": bool(settings.openai_compatible_base_url),
    }
    return [p for p in PROVIDERS if have[p]]


def default_model(provider: str) -> str:
    return {
        "anthropic": settings.claude_model,
        "gemini": settings.gemini_model,
        "groq": settings.groq_model,
        "openai_compatible": settings.openai_compatible_model,
    }[provider]


def _build(cfg: dict, temperature: float, gemini_key: str | None = None):
    provider = cfg["provider"]
    user_key = cfg.get("api_key")
    # A user may only choose the model when they pay for it (own key or own endpoint);
    # with the server's key the server's model is used, so nobody can pick a pricier one.
    model = cfg.get("model") if (user_key or provider == "openai_compatible") else None
    model = model or default_model(provider)

    if provider == "anthropic":
        # Current Claude models reject non-default sampling params, so temperature is not sent.
        return ChatAnthropic(
            model=model,
            api_key=user_key or settings.anthropic_api_key,
            max_tokens=8192,
            timeout=_TIMEOUT,
            max_retries=_SDK_RETRIES,
        )
    if provider == "gemini":
        key = user_key or gemini_key or (settings.google_api_keys or [""])[0]
        if not key:
            raise ValueError("No GOOGLE_API_KEY available for Gemini.")
        return ChatGoogleGenerativeAI(
            model=model, google_api_key=key, temperature=temperature,
            timeout=_TIMEOUT, max_retries=_SDK_RETRIES,
        )
    if provider == "groq":
        return ChatGroq(
            model=model, groq_api_key=user_key or settings.groq_api_key,
            temperature=temperature, timeout=_TIMEOUT, max_retries=_SDK_RETRIES,
        )
    if provider == "openai_compatible":
        base_url = cfg.get("base_url") or settings.openai_compatible_base_url
        if not base_url:
            raise ValueError("No base URL set for the OpenAI-compatible provider.")
        return ChatOpenAI(
            model=model, base_url=base_url,
            # Local servers ignore the key but the client requires a non-empty one.
            api_key=user_key or settings.openai_compatible_api_key or "not-needed",
            temperature=temperature, timeout=120.0, max_retries=_SDK_RETRIES,
        )
    raise ValueError(f"Unknown LLM provider: {provider}")


def _candidates(temperature: float) -> list:
    """Models to try in order: the active one first, then fallbacks."""
    override = llm_override.get()
    if override:
        return [_build(override, temperature)]

    primary = settings.llm_provider
    usable = available_providers()
    if primary not in usable:
        logger.warning("LLM_PROVIDER=%s has no key/URL configured; using %s", primary, usable)
    order = ([primary] if primary in usable else []) + [p for p in usable if p != primary]
    models = []
    for provider in order:
        try:
            if provider == "gemini":
                models += [_build({"provider": "gemini"}, temperature, k) for k in settings.google_api_keys]
            else:
                models.append(_build({"provider": provider}, temperature))
        except Exception as e:  # missing key for the configured default, etc.
            logger.warning("LLM provider %s unavailable: %s", provider, e)
    if not models:
        raise ValueError("No LLM provider is configured. Set LLM_PROVIDER and its API key in .env.")
    return models


def _structured(model, schema: Any):
    # Claude rejects forced tool choice on newer models; JSON-schema mode works on all of them.
    if isinstance(model, ChatAnthropic):
        return model.with_structured_output(schema, method="json_schema")
    return model.with_structured_output(schema)


def get_runnable(temperature: float = 0.2, schema: Any = None):
    """The active model (structured if `schema`), with fallbacks attached."""
    wrap = (lambda m: _structured(m, schema)) if schema is not None else (lambda m: m)
    first, *rest = [wrap(m) for m in _candidates(temperature)]
    return first.with_fallbacks(rest) if rest else first


def build_structured_chain(prompt: Any, schema: Any, temperature: float = 0.2):
    """`prompt | model.with_structured_output(schema)` on the active provider."""
    return prompt | get_runnable(temperature, schema)


def _is_prompt_runnable(prompt: Any) -> bool:
    return hasattr(prompt, "invoke") and hasattr(prompt, "__or__") and not isinstance(prompt, (str, list))


def invoke_llm(prompt: Any, temperature: float = 0.2, schema: Any = None):
    runnable = get_runnable(temperature, schema)
    if _is_prompt_runnable(prompt):
        return (prompt | runnable).invoke({})
    return runnable.invoke(prompt)


async def ainvoke_llm(prompt: Any, temperature: float = 0.2, schema: Any = None):
    runnable = get_runnable(temperature, schema)
    if _is_prompt_runnable(prompt):
        return await (prompt | runnable).ainvoke({})
    return await runnable.ainvoke(prompt)


def describe_active() -> dict:
    """Which provider/model a request would use (for the settings 'test' button)."""
    override = llm_override.get()
    provider = override["provider"] if override else settings.llm_provider
    cfg = override or {"provider": provider}
    model = cfg.get("model") if (cfg.get("api_key") or provider == "openai_compatible") else None
    return {"provider": provider, "model": model or default_model(provider), "user_override": bool(override)}


@lru_cache()
def get_groq_model(model_name: str | None = None, temperature: float = 0.2):
    """Server-key Groq model. Kept for scripts; agents should use get_runnable()."""
    return ChatGroq(
        model=model_name or settings.groq_model,
        groq_api_key=settings.groq_api_key,
        temperature=temperature,
    )


@lru_cache()
def get_huggingface_model(repo_id: str = "mistralai/Mistral-7B-Instruct-v0.2"):
    """
    Returns a configured HuggingFace model instance. Good for auxiliary subtasks.
    """
    llm = HuggingFaceEndpoint(
        repo_id=repo_id,
        temperature=0.2,
        huggingfacehub_api_token=settings.huggingface_api_key
    )
    return ChatHuggingFace(llm=llm)
