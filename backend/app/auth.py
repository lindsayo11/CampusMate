import httpx
from fastapi import Depends, Header, HTTPException
from .config import settings


def normalize_email(value: str | None) -> str | None:
    """Return a conservative canonical form for exact account lookup."""
    if not isinstance(value, str):
        return None
    value = value.strip().casefold()
    if not value or len(value) > 320 or "@" not in value:
        return None
    local, _, domain = value.rpartition("@")
    if not local or not domain or " " in value or "." not in domain:
        return None
    return value


def _resolve_user(authorization: str | None, x_user_id: str | None) -> dict[str, str | None]:
    if settings.demo_mode:
        return {"id": x_user_id or "demo-user", "email": None}
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    if not settings.supabase_url.startswith("https://") or not settings.supabase_anon_key:
        raise HTTPException(503, "身份服务尚未配置")
    try:
        response = httpx.get(
            settings.supabase_url.rstrip("/") + "/auth/v1/user",
            headers={"Authorization": authorization, "apikey": settings.supabase_anon_key},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "身份服务不可用") from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise HTTPException(503, "身份服务暂不可用")
    if response.status_code != 200:
        raise HTTPException(401, "登录已过期或无效")
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        raise HTTPException(503, "身份服务响应无效")
    user = payload.get("id")
    if not isinstance(user, str) or not user:
        raise HTTPException(401, "无效身份")
    email = normalize_email(payload.get("email"))
    return {"id": user, "email": email}


def authenticated_user(authorization: str | None = Header(default=None), x_user_id: str | None = Header(default=None)) -> dict[str, str | None]:
    return _resolve_user(authorization, x_user_id)


def actor_id(authorization: str | None = Header(default=None), x_user_id: str | None = Header(default=None)) -> str:
    return _resolve_user(authorization, x_user_id)["id"]  # type: ignore[return-value]


def require_admin(user: str = Depends(actor_id)):
    if user not in {v.strip() for v in settings.admin_user_ids.split(",") if v.strip()}:
        raise HTTPException(403, "需要管理员权限")
    return user
