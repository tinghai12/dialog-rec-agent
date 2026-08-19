"""购物车 / 订单 / 用户画像 接口（按用户隔离，带 JWT）。"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services import auth, cart as cart_service, events

router = APIRouter(prefix="/api", tags=["cart"])


def _uid(authorization: str | None) -> int:
    try:
        return auth.require_user(auth.parse_bearer(authorization))
    except auth.AuthError:
        raise HTTPException(status_code=401, detail="请先登录")


class CartAddRequest(BaseModel):
    product_id: int


@router.post("/cart/add")
def add_to_cart(req: CartAddRequest, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    items = cart_service.add_to_cart(uid, req.product_id)
    events.track(req.product_id, "cart", uid)
    return {"code": 0, "message": "ok", "data": {"cart": items}}


@router.get("/cart")
def get_cart(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    items = cart_service.get_cart(uid)
    return {"code": 0, "message": "ok", "data": {"cart": items}}


@router.delete("/cart/{item_id}")
def remove_cart_item(item_id: int, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    items = cart_service.remove_cart_item(uid, item_id)
    return {"code": 0, "message": "ok", "data": {"cart": items}}


@router.post("/order")
def create_order(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    order = cart_service.create_order(uid)
    events.track([p["id"] for p in order.get("products", [])], "order", uid)
    return {"code": 0, "message": "ok", "data": order}


@router.get("/order")
def get_orders(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    orders = cart_service.get_orders(uid)
    return {"code": 0, "message": "ok", "data": {"orders": orders}}


@router.get("/profile")
def get_profile(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    profile = cart_service.build_profile(uid)
    return {"code": 0, "message": "ok", "data": profile}
