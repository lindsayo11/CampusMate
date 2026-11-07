"""Provider contract and assistant integration tests; no paid external calls."""
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import agent_generation
from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "unit-test-key")
    monkeypatch.setattr(settings, "development_dify_app_key", "")
    monkeypatch.setattr(settings, "tavily_api_key", "")
    monkeypatch.setattr(settings, "jev_api_key", "")


def response(url, content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]},
                          request=httpx.Request("POST", url))


def test_model_receives_actual_query_history_and_original_evidence(monkeypatch):
    def provider(url, **kwargs):
        payload = kwargs["json"]
        assert payload["thinking"] == {"type": "disabled"}
        messages = payload["messages"]
        assert messages[-1] == {"role": "user", "content": "回复我 hello"}
        assert {"role": "assistant", "content": "你好，小林。"} in messages
        assert "原文要求" in messages[-2]["content"]
        assert "unit-test-key" not in str(messages)
        return response(url, "hello")
    monkeypatch.setattr(agent_generation.httpx, "post", provider)
    result = agent_generation.explain("回复我 hello", {"references": [{"quote": "原文要求"}]},
        "private-user", history=[{"query": "叫我小林", "result": {"model_explanation": "你好，小林。"}}])
    assert result == "hello"


@pytest.mark.parametrize("payload", [{}, [], {"choices": []}, {"choices": [None]},
    {"choices": [{"message": {"content": "", "reasoning_content": "private reasoning"}}]}])
def test_invalid_or_reasoning_only_output_is_an_error(monkeypatch, payload):
    monkeypatch.setattr(agent_generation.httpx, "post", lambda url, **kw:
        httpx.Response(200, json=payload, request=httpx.Request("POST", url)))
    with pytest.raises(HTTPException) as exc:
        agent_generation.explain("你好", {}, "test")
    assert exc.value.status_code == 502


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_provider_errors_are_safe_not_fake_answers(monkeypatch, status, caplog):
    monkeypatch.setattr(agent_generation.httpx, "post", lambda url, **kw:
        httpx.Response(status, text="secret-provider-body", request=httpx.Request("POST", url)))
    with pytest.raises(HTTPException) as exc:
        agent_generation.explain("private-prompt", {}, "private-user")
    assert exc.value.status_code == 502
    assert "secret-provider-body" not in exc.value.detail + caplog.text
    assert "unit-test-key" not in caplog.text
    assert "private-prompt" not in caplog.text


def test_timeout_has_explicit_error(monkeypatch):
    def timeout(*a, **kw):
        raise httpx.ReadTimeout("private-provider-url")
    monkeypatch.setattr(agent_generation.httpx, "post", timeout)
    with pytest.raises(HTTPException) as exc:
        agent_generation.explain("你好", {}, "test")
    assert exc.value.status_code == 504


def test_chat_carries_history_and_rejects_other_users(monkeypatch):
    prompts = []
    def provider(url, **kw):
        prompts.append(kw["json"]["messages"])
        return response(url, "hello" if len(prompts) == 1 else "你让我回复 hello。")
    monkeypatch.setattr(agent_generation.httpx, "post", provider)
    user = {"x-user-id": str(uuid4())}
    with TestClient(app) as client:
        first = client.post("/v1/development-agent/chat", headers=user, json={"query": "回复我 hello"})
        assert first.status_code == 200, first.text
        first = first.json()
        assert first["result"]["model_explanation"] == "hello"
        assert first["answer_provider"] == "deepseek"
        cid = first["conversation_id"]
        second = client.post("/v1/development-agent/chat", headers=user,
            json={"query": "刚才让我回复什么？", "conversation_id": cid})
        assert second.status_code == 200, second.text
        assert {"role": "assistant", "content": "hello"} in prompts[-1]
        assert client.post("/v1/development-agent/chat", headers={"x-user-id": str(uuid4())},
            json={"query": "继续", "conversation_id": cid}).status_code == 404
        assert len(prompts) == 2


def test_unconfigured_chat_is_503_without_saved_fake_turn(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    user = {"x-user-id": str(uuid4())}
    with TestClient(app) as client:
        reply = client.post("/v1/development-agent/chat", headers=user, json={"query": "你好"})
        assert reply.status_code == 503
        assert "尚未配置" in reply.json()["detail"]
        assert client.get("/v1/development-agent/conversations", headers=user).json() == []
        status = client.get("/v1/development-agent/status", headers=user).json()
        assert status["mode"] == "unavailable" and status["answer_configured"] is False


def test_local_notices_are_answered_by_model_not_match_label(monkeypatch):
    refs = [{"url": "https://example.edu/notice", "quote": "申请者须具备本校推免资格", "location": "第一条"}]
    monkeypatch.setattr("app.agent_retrieval.retrieve", lambda *a, **kw: refs)
    monkeypatch.setattr("app.development_agent.catalog", lambda **kw: {"items": [], "total": 0})
    def no_web(*a, **kw):
        pytest.fail("A stored-notice query should not require online research")
    monkeypatch.setattr("app.web_research.research", no_web)
    def provider(url, **kw):
        assert "申请者须具备本校推免资格" in kw["json"]["messages"][-2]["content"]
        return response(url, "这份公告要求具备本校推免资格。[本地1]")
    monkeypatch.setattr(agent_generation.httpx, "post", provider)
    with TestClient(app) as client:
        reply = client.post("/v1/development-agent/chat", json={"query": "保研有什么要求"})
        assert reply.status_code == 200, reply.text
        data = reply.json()
        assert data["tool"] == "search"
        assert "[本地1]" in data["result"]["model_explanation"]
        assert data["result"]["references"] == refs


def test_read_tool_survives_outage_with_explicit_notice(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    with TestClient(app) as client:
        reply = client.post("/v1/development-agent/chat", json={"query": "简历如何改", "intent": "materials"})
        assert reply.status_code == 200
        result = reply.json()
        assert result["answer_provider"] is None
        assert result["result"]["suggestions"]
        assert "尚未生成 AI 解读" in result["result"]["model_notice"]
        assert "model_explanation" not in result["result"]


def test_retrieval_does_not_mix_employment_with_recommendation(monkeypatch):
    from types import SimpleNamespace
    from app import agent_retrieval
    def record(code, title, quote):
        return SimpleNamespace(id=code), {"items": [{"title": title, "paths": [{"code": code}]}],
            "evidence": [{"id": code, "quote_or_normalized_fact": quote, "evidence_location": "正文"}],
            "document": {"canonical_url": "https://example.edu/"+code, "content_hash": code}}
    monkeypatch.setattr(agent_retrieval, "path_codes", lambda db, code: {code})
    monkeypatch.setattr(agent_retrieval, "visible", lambda db: [
        record("employment", "就业公告", "申请条件与要求：本科毕业。"),
        record("recommendation_exemption", "接收推免生公告", "英语六级成绩须达 425 分。")])
    refs = agent_retrieval.retrieve(None, "保研有什么要求？请引用已入库的公告。", "recommendation_exemption")
    assert len(refs) == 1
    assert refs[0]["publication_id"] == "recommendation_exemption"
    assert "六级" in refs[0]["quote"]
