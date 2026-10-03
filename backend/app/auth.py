import httpx
from fastapi import Depends, Header, HTTPException
from .config import settings


def actor_id(authorization: str | None = Header(default=None), x_user_id: str | None = Header(default=None)) -> str:
    if settings.demo_mode:
        return x_user_id or "demo-user"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    if not settings.supabase_url.startswith("https://") or not settings.supabase_anon_key:
        raise HTTPException(503, "身份服务尚未配置")
    try:
        response = httpx.get(settings.supabase_url.rstrip("/") + "/auth/v1/user", headers={"Authorization": authorization, "apikey": settings.supabase_anon_key}, timeout=10)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "身份服务不可用") from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise HTTPException(503, "身份服务暂不可用")
    if response.status_code != 200:
        raise HTTPException(401, "登录已过期或无效")
    try:
        user = response.json().get("id")
    except (ValueError, AttributeError):
        raise HTTPException(503, "身份服务响应无效")
    if not isinstance(user, str) or not user:
        raise HTTPException(401, "无效身份")
    return user


def require_admin(user: str = Depends(actor_id)):
    if user not in {v.strip() for v in settings.admin_user_ids.split(",") if v.strip()}:
        raise HTTPException(403, "需要管理员权限")
    return user
