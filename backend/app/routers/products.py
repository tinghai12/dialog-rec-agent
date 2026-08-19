"""商品接口：列表 / 详情 / 相似 / 自然语言搜索。

列表与搜索返回商家维护的营销位字段，供前台海报式卡片渲染。
"""
from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services import auth, catalog, events, favorites, search, similar

router = APIRouter(prefix="/api/products", tags=["products"])

# 卡片展示所需的营销位字段
_CARD_MARKETING = (
    "shop_name", "main_image", "poster_bg", "poster_headline", "poster_subline",
    "poster_specs", "poster_price_label", "promo_banner", "promo_banner_style",
    "title_prefix", "rank_label", "final_price", "saved_amount", "installment",
    "service_tags", "sold_count", "repeat_buyers",
)


def _card(p: dict, with_pros: bool = False) -> dict:
    """商品卡片的统一输出结构（基础字段 + 营销位）。"""
    item = {
        "id": p["id"],
        "title": p["title"],
        "brand": p["brand"],
        "category": p["category"],
        "price": float(p["price"]),
        "attributes": p.get("attributes", {}),
    }
    if with_pros:
        item["pros"] = p.get("pros", [])
        item["cons"] = p.get("cons", [])
    for key in _CARD_MARKETING:
        item[key] = p.get(key)
    return item


@router.get("")
def list_products():
    items = [_card(p, with_pros=True) for p in catalog.get_all()]
    return {"code": 0, "message": "ok", "data": items}


class SearchRequest(BaseModel):
    query: str
    category: str | None = None
    session_id: str | None = None


@router.post("/search")
def search_products(req: SearchRequest, authorization: str | None = Header(None)):
    items = search.search_nl(req.query, req.category)
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    # 搜索结果即曝光，记入商家看板
    events.track([i["id"] for i in items], "recommend", uid, req.session_id or "")
    return {"code": 0, "message": "ok", "data": {"results": items}}


@router.get("/{product_id}/similar")
def similar_products(product_id: int):
    """内容相似商品推荐（ItemCF 内容化变体）。"""
    items = [_card(p) for p in similar.similar_by_id(product_id)]
    return {"code": 0, "message": "ok", "data": items}


@router.get("/{product_id}")
def product_detail(product_id: int, authorization: str | None = Header(None)):
    p = catalog.find_by_id(product_id)
    if p is None:
        return {"code": 1, "message": "商品不存在"}
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    data = _card(p, with_pros=True)
    data["reviews"] = p.get("reviews", [])[:5]
    data["similar"] = [_card(s) for s in similar.similar_by_id(product_id)]
    events.track(product_id, "view", uid)
    if uid is not None:
        try:
            data["is_favorite"] = favorites.is_favorite(uid, product_id)
        except Exception:
            data["is_favorite"] = False
    return {"code": 0, "message": "ok", "data": data}
