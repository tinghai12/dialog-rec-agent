"""购物车 / 订单 / 收货地址 / 用户画像 接口（按用户隔离，带 JWT）。"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services import address as address_svc, auth, cart as cart_service, events, order as order_svc

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


# ============ 订单 ============

class CreateOrderRequest(BaseModel):
    address_id: int | None = None
    session_id: str | None = None


@router.post("/order")
def create_order(req: CreateOrderRequest | None = None, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    req = req or CreateOrderRequest()
    try:
        orders = order_svc.create_order(uid, req.address_id, req.session_id or "")
    except order_svc.OrderError as e:
        return {"code": 1, "message": str(e)}
    except address_svc.AddressError as e:
        return {"code": 1, "message": str(e)}
    for o in orders:
        events.track([p["id"] for p in o.get("products", [])], "order", uid)
    # 兼容旧前端：data 里同时给出首个订单号
    return {
        "code": 0, "message": "下单成功，等待商家接单",
        "data": {"orders": orders, "order_no": orders[0]["order_no"], "total_amount": orders[0]["total_amount"]},
    }


@router.get("/order")
def get_orders(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    return {"code": 0, "message": "ok", "data": {"orders": order_svc.list_orders(uid)}}


@router.get("/order/{order_no}")
def get_order(order_no: str, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    try:
        data = order_svc.get_order(uid, order_no)
    except order_svc.OrderError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "ok", "data": data}


class RouteRequest(BaseModel):
    route: list[list[float]]


@router.post("/order/{order_no}/route")
def save_route(order_no: str, req: RouteRequest, authorization: str | None = Header(None)):
    """前端用高德路径规划算好道路点后回传，后续复用。"""
    uid = _uid(authorization)
    try:
        n = order_svc.save_route(uid, order_no, req.route)
    except order_svc.OrderError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "ok", "data": {"points": n}}


class AftersaleRequest(BaseModel):
    type: str = "refund"
    reason: str = ""


@router.post("/order/{order_no}/aftersale")
def apply_aftersale(order_no: str, req: AftersaleRequest, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    try:
        data = order_svc.apply_aftersale(uid, order_no, req.type, req.reason)
    except order_svc.OrderError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "售后申请已提交，等商家处理", "data": data}


# ============ 收货地址 ============

class AddressPayload(BaseModel):
    receiver: str
    phone: str
    province: str = ""
    city: str = ""
    district: str = ""
    detail: str
    lng: float | None = None
    lat: float | None = None
    is_default: bool = False


@router.get("/addresses")
def list_addresses(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    return {"code": 0, "message": "ok", "data": {"addresses": address_svc.list_addresses(uid)}}


@router.post("/addresses")
def create_address(req: AddressPayload, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    try:
        data = address_svc.create(uid, req.model_dump())
    except address_svc.AddressError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已添加", "data": data}


@router.put("/addresses/{address_id}")
def update_address(address_id: int, req: AddressPayload, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    try:
        data = address_svc.update(uid, address_id, req.model_dump())
    except address_svc.AddressError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已保存", "data": data}


@router.post("/addresses/{address_id}/default")
def set_default_address(address_id: int, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    try:
        data = address_svc.set_default(uid, address_id)
    except address_svc.AddressError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已设为默认", "data": data}


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, authorization: str | None = Header(None)):
    uid = _uid(authorization)
    try:
        address_svc.delete(uid, address_id)
    except address_svc.AddressError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已删除", "data": None}


@router.get("/profile")
def get_profile(authorization: str | None = Header(None)):
    uid = _uid(authorization)
    profile = cart_service.build_profile(uid)
    return {"code": 0, "message": "ok", "data": profile}
