"""AI provider info + connection test for the Profile → AI provider panel."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import require_user_id
from app.dependencies.llm import llm_context
from app.utils.llm_factory import PROVIDERS, ainvoke_llm, available_providers, default_model, describe_active
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/llm", tags=["AI provider"])


@router.get("/providers")
def list_providers():
    """Which providers exist, which the server can serve with its own keys, and the default."""
    server = set(available_providers())
    return {
        "default": settings.llm_provider,
        "providers": [
            {"id": p, "server_key": p in server, "default_model": default_model(p)} for p in PROVIDERS
        ],
    }


@router.post("/test", dependencies=[Depends(llm_context)])
async def test_connection(user_id: str = Depends(require_user_id)):
    """Send one tiny prompt through whatever provider this request resolves to."""
    active = describe_active()
    try:
        reply = await ainvoke_llm("Reply with the single word: ok", temperature=0.0)
    except Exception as e:
        logger.warning("LLM test failed for %s: %s", active["provider"], type(e).__name__)
        raise HTTPException(status_code=502, detail=f"{active['provider']} did not answer: {str(e)[:200]}")
    text = reply.content if isinstance(reply.content, str) else str(reply.content)
    return {**active, "reply": text.strip()[:80]}
