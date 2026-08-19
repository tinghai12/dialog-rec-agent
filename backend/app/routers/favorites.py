"""收藏接口（按用户隔离，带 JWT）。"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services import auth, favorites

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


def _uid(authorization: str | None) -> int:
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        return auth.require_user(token)
    except auth.AuthError:
        raise HTTPException(status_code=401, detail="请先登录")


class FavRequest(BaseModel):
    product_id: int


@router.post("/add")
def add(req: FavRequest, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    items = favorites.add(uid, req.product_id)
    return {"code": 0, "message": "ok", "data": {"favorites": items}}


@router.get("")
def list_all(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    items = favorites.list_favorites(uid)
    return {"code": 0, "message": "ok", "data": {"favorites": items}}


@router.delete("/{product_id}")
def remove(product_id: int, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    items = favorites.remove(uid, product_id)
    return {"code": 0, "message": "ok", "data": {"favorites": items}}
