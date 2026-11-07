"""Optional high-confidence route hint from TypeSafe SystemOne/Jev."""

from __future__ import annotations

import httpx

from .config import settings

ROUTES = {
    "chat": "普通问候、闲聊或不需要外部事实",
    "search": "需要联网或资料库查找事实、日期、要求、公告",
    "plan": "用户明确要求制定或修改计划",
    "eligibility": "用户要求资格条件核对",
    "profile": "用户询问个人画像或资料",
    "paths": "用户明确要求比较发展方向或查看路径目录",
}


def route_hint(query: str, history: list[dict] | None = None) -> tuple[str | None, float]:
    """Return a route only when Jev is configured and sufficiently certain."""
    if not settings.jev_api_key.strip() or not query.strip():
        return None, 0.0
    body = {
        "model": settings.jev_model,
        "state": {"query": query[:6000], "history": (history or [])[-4:]},
        "questions": {
            "route": {
                "type": "choice",
                "instructions": "选择最适合处理用户消息的路线。犹豫时选择 chat。",
                "criteria": ROUTES,
            }
        },
    }
    try:
        response = httpx.post(
            settings.jev_api_base.rstrip("/") + "/systemone",
            headers={"Authorization": "Bearer " + settings.jev_api_key},
            json=body,
            timeout=8,
        )
        response.raise_for_status()
        answer = response.json().get("answers", {}).get("route", {})
        route = answer.get("choice")
        confidence = float(answer.get("confidence") or 0)
        if route in ROUTES and confidence >= 0.75:
            return route, confidence
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        pass
    return None, 0.0
