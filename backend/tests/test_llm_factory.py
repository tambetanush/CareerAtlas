"""Tests for the provider switch in app.utils.llm_factory and app.dependencies.llm."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from app.dependencies import llm as llm_dep
from app.utils import llm_factory


@pytest.fixture
def server_keys(monkeypatch):
    s = llm_factory.settings
    monkeypatch.setattr(s, "llm_provider", "groq")
    monkeypatch.setattr(s, "groq_api_key", "groq-key")
    monkeypatch.setattr(s, "google_api_keys", ["g1", "g2"])
    monkeypatch.setattr(s, "anthropic_api_key", "")
    monkeypatch.setattr(s, "openai_compatible_base_url", "")
    llm_factory.llm_override.set(None)
    return s


def test_default_order_is_primary_then_each_gemini_key(server_keys):
    models = llm_factory._candidates(0.2)
    names = [type(m).__name__ for m in models]
    assert names == ["ChatGroq", "ChatGoogleGenerativeAI", "ChatGoogleGenerativeAI"]
    # one Gemini model per key keeps key rotation on failure
    assert [m.google_api_key.get_secret_value() for m in models[1:]] == ["g1", "g2"]


def test_user_override_has_no_cloud_fallback(server_keys):
    llm_factory.llm_override.set({"provider": "openai_compatible", "base_url": "http://localhost:11434/v1", "model": "qwen3"})
    models = llm_factory._candidates(0.2)
    assert len(models) == 1 and type(models[0]).__name__ == "ChatOpenAI"
    assert models[0].model_name == "qwen3"


def test_server_key_ignores_user_model_but_own_key_honours_it(server_keys):
    with_server_key = llm_factory._build({"provider": "groq", "model": "pricey-model"}, 0.2)
    assert with_server_key.model_name == server_keys.groq_model
    with_own_key = llm_factory._build({"provider": "groq", "model": "pricey-model", "api_key": "mine"}, 0.2)
    assert with_own_key.model_name == "pricey-model"


def test_claude_is_built_without_temperature(server_keys):
    model = llm_factory._build({"provider": "anthropic", "api_key": "sk-test"}, 0.7)
    assert model.model == server_keys.claude_model
    assert model.temperature is None


def test_default_without_key_is_skipped(server_keys, monkeypatch):
    monkeypatch.setattr(server_keys, "llm_provider", "anthropic")  # no ANTHROPIC_API_KEY yet
    names = [type(m).__name__ for m in llm_factory._candidates(0.2)]
    assert names and "ChatAnthropic" not in names


def test_no_provider_configured_raises(server_keys, monkeypatch):
    monkeypatch.setattr(server_keys, "groq_api_key", "")
    monkeypatch.setattr(server_keys, "google_api_keys", [])
    with pytest.raises(ValueError, match="No LLM provider"):
        llm_factory._candidates(0.2)


def test_invoke_llm_falls_back_to_next_model(server_keys, monkeypatch):
    def broken(_):
        raise RuntimeError("primary down")

    monkeypatch.setattr(llm_factory, "_candidates", lambda t: [RunnableLambda(broken), RunnableLambda(lambda _: "fallback-ok")])
    assert llm_factory.invoke_llm("hi") == "fallback-ok"


async def test_ainvoke_llm_uses_override_only(server_keys, monkeypatch):
    seen = {}

    def fake_candidates(_t):
        seen["override"] = llm_factory.llm_override.get()
        return [RunnableLambda(lambda _: "ok")]

    monkeypatch.setattr(llm_factory, "_candidates", fake_candidates)
    llm_factory.llm_override.set({"provider": "groq", "api_key": "k"})
    assert await llm_factory.ainvoke_llm("hi") == "ok"
    assert seen["override"]["provider"] == "groq"


# ── request dependency ───────────────────────────────────────────────────────

def _app():
    app = FastAPI()

    @app.get("/sync", dependencies=[Depends(llm_dep.llm_context)])
    def sync_route():  # runs in the threadpool, like deep_research
        return {"active": llm_factory.describe_active()}

    return TestClient(app)


def test_override_reaches_sync_route(server_keys):
    res = _app().get("/sync", headers={"X-LLM-Provider": "groq", "X-LLM-Api-Key": "mine", "X-LLM-Model": "m1"})
    assert res.status_code == 200
    assert res.json()["active"] == {"provider": "groq", "model": "m1", "user_override": True}


def test_no_headers_means_server_default(server_keys):
    res = _app().get("/sync")
    assert res.json()["active"]["user_override"] is False


def test_private_base_url_rejected_on_hosted_deploy(server_keys, monkeypatch):
    monkeypatch.setattr(llm_dep.settings, "allow_private_llm_urls", False)
    for url in ("http://127.0.0.1:11434/v1", "http://169.254.169.254/latest", "http://localhost:8000"):
        res = _app().get("/sync", headers={"X-LLM-Provider": "openai_compatible", "X-LLM-Base-URL": url})
        assert res.status_code == 400, url


def test_private_base_url_allowed_when_self_hosting(server_keys, monkeypatch):
    monkeypatch.setattr(llm_dep.settings, "allow_private_llm_urls", True)
    res = _app().get("/sync", headers={"X-LLM-Provider": "openai_compatible", "X-LLM-Base-URL": "http://localhost:11434/v1"})
    assert res.status_code == 200


def test_cloud_provider_without_any_key_rejected(server_keys):
    res = _app().get("/sync", headers={"X-LLM-Provider": "anthropic"})
    assert res.status_code == 400


def test_unknown_provider_rejected(server_keys):
    assert _app().get("/sync", headers={"X-LLM-Provider": "skynet"}).status_code == 400
