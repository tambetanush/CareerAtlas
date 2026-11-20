"""Per-request LLM provider override, read from headers the frontend sends.

The user's choice (and their own API key, if any) lives only in their browser and
arrives on each request as X-LLM-* headers. Nothing here is stored or logged.
"""
import asyncio
import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from app.config import settings
from app.utils.llm_factory import PROVIDERS, available_providers, llm_override


async def _check_base_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Model base URL must be an http(s) URL.")
    if settings.allow_private_llm_urls:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError:
        raise HTTPException(status_code=400, detail="Model base URL host could not be resolved.")
    # shortcut: checks the resolved IPs once, so DNS rebinding could still slip through; pin the IP in the client if this backend ever holds secrets worth that.
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise HTTPException(
                status_code=400,
                detail="This server can't reach private or local addresses. "
                "To use a model on your own machine, run CareerAtlas locally.",
            )


async def llm_context(request: Request) -> None:
    """FastAPI dependency: set the LLM override for this request, if the user chose one.

    Async on purpose: it runs in the request's own context, so the ContextVar it sets is
    copied into the threadpool for sync routes and into tasks spawned by async ones.
    """
    provider = (request.headers.get("x-llm-provider") or "").strip().lower()
    if not provider:
        llm_override.set(None)
        return
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown AI provider '{provider}'.")

    cfg = {
        "provider": provider,
        "model": (request.headers.get("x-llm-model") or "").strip() or None,
        "base_url": (request.headers.get("x-llm-base-url") or "").strip() or None,
        "api_key": (request.headers.get("x-llm-api-key") or "").strip() or None,
    }
    if provider == "openai_compatible":
        if not (cfg["base_url"] or settings.openai_compatible_base_url):
            raise HTTPException(status_code=400, detail="Add a base URL for your model server.")
        if cfg["base_url"]:
            await _check_base_url(cfg["base_url"])
    elif not cfg["api_key"] and provider not in available_providers():
        raise HTTPException(status_code=400, detail=f"Add your own API key to use {provider} here.")
    llm_override.set(cfg)
