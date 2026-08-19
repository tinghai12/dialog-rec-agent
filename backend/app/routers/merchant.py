"""商家端接口：商品管理 / 营销位 / 主图上传 / 数据看板。

所有接口都要求 role=merchant，且只能操作自己店铺的商品。
"""
from fastapi import APIRouter, File, Header, UploadFile
from pydantic import BaseModel

from app.services import auth, merchant

router = APIRouter(prefix="/api/merchant", tags=["merchant"])


def _merchant_id(authorization: str | None) -> int:
    return auth.require_merchant(auth.parse_bearer(authorization))


def _err(e: Exception, code: int = 1):
    return {"code": code, "message": str(e)}


class ProductPayload(BaseModel):
    """商品基础字段 + 营销位字段，全部可选（创建时 title/category/price 必填）。"""
    title: str | None = None
    brand: str | None = None
    category: str | None = None
    price: float | None = None
    is_on_sale: int | None = None
    attributes: dict | None = None
    pros: list[str] | None = None
    cons: list[str] | None = None
    # 营销位
    main_image: str | None = None
    poster_bg: str | None = None
    poster_headline: str | None = None
    poster_subline: str | None = None
    poster_specs: list[str] | None = None
    poster_price_label: str | None = None
    promo_banner: str | None = None
    promo_banner_style: str | None = None
    title_prefix: str | None = None
    rank_label: str | None = None
    final_price: float | None = None
    saved_amount: float | None = None
    installment: str | None = None
    service_tags: list[str] | None = None
    sold_count: int | None = None
    repeat_buyers: int | None = None
    promo_start: str | None = None
    promo_end: str | None = None

    def changes(self) -> dict:
        """只保留显式传入的字段，避免把未填字段清空。"""
        return self.model_dump(exclude_unset=True)


class OnSalePayload(BaseModel):
    is_on_sale: bool


@router.get("/products")
def list_products(
    keyword: str = "", category: str = "", page: int = 1, page_size: int = 20,
    authorization: str | None = Header(None),
):
    try:
        mid = _merchant_id(authorization)
        data = merchant.list_products(mid, keyword, category, page, page_size)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/dashboard")
def dashboard(days: int = 30, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        data = merchant.dashboard(mid, days)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/products/{product_id}")
def get_product(product_id: int, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        data = merchant.get_product(mid, product_id)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "ok", "data": data}


@router.post("/products")
def create_product(req: ProductPayload, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        data = merchant.create_product(mid, req.changes())
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "创建成功", "data": data}


@router.put("/products/{product_id}")
def update_product(product_id: int, req: ProductPayload, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        data = merchant.update_product(mid, product_id, req.changes())
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "保存成功", "data": data}


@router.delete("/products/{product_id}")
def delete_product(product_id: int, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        merchant.delete_product(mid, product_id)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "已删除", "data": None}


@router.post("/products/{product_id}/on-sale")
def set_on_sale(product_id: int, req: OnSalePayload, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        data = merchant.toggle_on_sale(mid, product_id, req.is_on_sale)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "上架成功" if req.is_on_sale else "已下架", "data": data}


@router.post("/products/{product_id}/image")
async def upload_image(
    product_id: int, file: UploadFile = File(...), authorization: str | None = Header(None),
):
    try:
        mid = _merchant_id(authorization)
        content = await file.read()
        url = merchant.save_image(mid, product_id, file.filename, content)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "上传成功", "data": {"main_image": url}}


@router.delete("/products/{product_id}/image")
def remove_image(product_id: int, authorization: str | None = Header(None)):
    try:
        mid = _merchant_id(authorization)
        merchant.delete_image(mid, product_id)
    except (auth.AuthError, merchant.MerchantError) as e:
        return _err(e)
    return {"code": 0, "message": "已清除主图", "data": None}
