"""商家端服务：商品 CRUD / 营销位维护 / 主图上传 / 数据看板。

所有写操作都以 merchant_id 校验归属，商家只能操作自己店铺的商品。
写完调用 catalog.invalidate()，让前台立刻看到最新数据。
"""
import json
import re
import uuid
from pathlib import Path

import pymysql

from app.core.config import settings
from app.services import catalog

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
UPLOAD_URL_PREFIX = "/static/uploads"
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# 商品基础字段（商家可改）
BASE_FIELDS = ("title", "brand", "category", "price", "is_on_sale")
JSON_BASE_FIELDS = ("attributes", "pros", "cons")

# 营销位字段（商家可改）
MARKETING_FIELDS = (
    "main_image", "poster_bg", "poster_headline", "poster_subline", "poster_specs",
    "poster_price_label", "promo_banner", "promo_banner_style", "title_prefix",
    "rank_label", "final_price", "saved_amount", "installment", "service_tags",
    "sold_count", "repeat_buyers", "promo_start", "promo_end",
)
JSON_MARKETING_FIELDS = ("poster_specs", "service_tags")

BANNER_STYLES = ("none", "tmall", "subsidy", "live")
POSTER_BGS = ("", "dark", "blue", "purple", "red", "green", "ink")


class MerchantError(Exception):
    pass


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _shop_name(cur, merchant_id: int) -> str:
    cur.execute("SELECT shop_name, nickname FROM users WHERE id=%s", (merchant_id,))
    row = cur.fetchone() or {}
    return row.get("shop_name") or row.get("nickname") or ""


# ============ 查询 ============

def list_products(merchant_id: int, keyword: str = "", category: str = "",
                  page: int = 1, page_size: int = 20) -> dict:
    """分页列出该商家的商品。"""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    where = ["merchant_id = %s"]
    params: list = [merchant_id]
    if keyword:
        where.append("(title LIKE %s OR brand LIKE %s)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if category:
        where.append("category = %s")
        params.append(category)
    clause = " AND ".join(where)

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM products WHERE {clause}", params)
            total = cur.fetchone()["n"]
            cur.execute(
                f"SELECT id, title, brand, category, price, attributes, pros, cons, is_on_sale, "
                f"merchant_id, shop_name, main_image, poster_bg, poster_headline, poster_subline, "
                f"poster_specs, poster_price_label, promo_banner, promo_banner_style, title_prefix, "
                f"rank_label, final_price, saved_amount, installment, service_tags, sold_count, "
                f"repeat_buyers, promo_start, promo_end, updated_at "
                f"FROM products WHERE {clause} ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s",
                params + [page_size, (page - 1) * page_size],
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_row_out(r) for r in rows],
    }


def get_product(merchant_id: int, product_id: int) -> dict:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id=%s", (product_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise MerchantError("商品不存在")
    if row.get("merchant_id") != merchant_id:
        raise MerchantError("无权操作该商品")
    return _row_out(row)


def _row_out(row: dict) -> dict:
    out = dict(row)
    for key in ("attributes", "pros", "cons", "reviews", "poster_specs", "service_tags"):
        value = out.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = None
        out[key] = value if value is not None else ({} if key == "attributes" else [])
    out.pop("reviews", None)
    out["price"] = float(out["price"])
    for key in ("final_price", "saved_amount"):
        out[key] = float(out[key]) if out.get(key) is not None else None
    for key in ("promo_start", "promo_end", "updated_at", "created_at"):
        if out.get(key):
            out[key] = out[key].strftime("%Y-%m-%d %H:%M:%S")
    return out


# ============ 写入 ============

def _clean_base(data: dict, partial: bool) -> dict:
    """校验并抽取商品基础字段。partial=True 时只处理传入的键。"""
    out: dict = {}
    for key in BASE_FIELDS:
        if key not in data:
            if partial:
                continue
            if key == "is_on_sale":
                out[key] = 1
                continue
            raise MerchantError(f"缺少字段：{key}")
        value = data[key]
        if key == "price":
            try:
                value = round(float(value), 2)
            except (TypeError, ValueError):
                raise MerchantError("价格必须是数字")
            if value <= 0:
                raise MerchantError("价格必须大于 0")
        elif key == "is_on_sale":
            value = 1 if value in (1, True, "1", "true") else 0
        else:
            value = str(value or "").strip()
            if key in ("title", "category") and not value:
                raise MerchantError(f"{key} 不能为空")
        out[key] = value
    for key in JSON_BASE_FIELDS:
        if key in data:
            out[key] = json.dumps(data[key] or ([] if key != "attributes" else {}), ensure_ascii=False)
    return out


def _clean_marketing(data: dict) -> dict:
    """校验并抽取营销位字段（只处理传入的键）。"""
    out: dict = {}
    for key in MARKETING_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if key in JSON_MARKETING_FIELDS:
            if not isinstance(value, list):
                raise MerchantError(f"{key} 必须是数组")
            out[key] = json.dumps([str(v) for v in value][:6], ensure_ascii=False)
        elif key in ("final_price", "saved_amount"):
            if value in (None, ""):
                out[key] = None
            else:
                try:
                    out[key] = round(float(value), 2)
                except (TypeError, ValueError):
                    raise MerchantError(f"{key} 必须是数字")
                if out[key] < 0:
                    raise MerchantError(f"{key} 不能为负")
        elif key in ("sold_count", "repeat_buyers"):
            try:
                out[key] = max(0, int(value or 0))
            except (TypeError, ValueError):
                raise MerchantError(f"{key} 必须是整数")
        elif key in ("promo_start", "promo_end"):
            out[key] = value or None
        elif key == "promo_banner_style":
            value = str(value or "none")
            if value not in BANNER_STYLES:
                raise MerchantError("促销条样式非法")
            out[key] = value
        elif key == "poster_bg":
            value = str(value or "")
            if value not in POSTER_BGS:
                raise MerchantError("海报底色非法")
            out[key] = value
        else:
            out[key] = str(value or "").strip()
    return out


def create_product(merchant_id: int, data: dict) -> dict:
    base = _clean_base(data, partial=False)
    marketing = _clean_marketing(data)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            fields = {**base, **marketing, "merchant_id": merchant_id,
                      "shop_name": _shop_name(cur, merchant_id), "reviews": json.dumps([])}
            cols = ", ".join(fields)
            placeholders = ", ".join(["%s"] * len(fields))
            cur.execute(
                f"INSERT INTO products ({cols}) VALUES ({placeholders})",
                list(fields.values()),
            )
            new_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    catalog.invalidate()
    return get_product(merchant_id, new_id)


def update_product(merchant_id: int, product_id: int, data: dict) -> dict:
    get_product(merchant_id, product_id)          # 校验归属
    fields = {**_clean_base(data, partial=True), **_clean_marketing(data)}
    if not fields:
        raise MerchantError("没有需要更新的字段")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            assignments = ", ".join(f"{k}=%s" for k in fields)
            cur.execute(
                f"UPDATE products SET {assignments} WHERE id=%s AND merchant_id=%s",
                list(fields.values()) + [product_id, merchant_id],
            )
        conn.commit()
    finally:
        conn.close()
    catalog.invalidate()
    return get_product(merchant_id, product_id)


def delete_product(merchant_id: int, product_id: int) -> None:
    get_product(merchant_id, product_id)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cart_items WHERE product_id=%s", (product_id,))
            cur.execute("DELETE FROM favorites WHERE product_id=%s", (product_id,))
            cur.execute("DELETE FROM products WHERE id=%s AND merchant_id=%s", (product_id, merchant_id))
        conn.commit()
    finally:
        conn.close()
    catalog.invalidate()


def toggle_on_sale(merchant_id: int, product_id: int, on_sale: bool) -> dict:
    return update_product(merchant_id, product_id, {"is_on_sale": 1 if on_sale else 0})


# ============ 主图上传 ============

def save_image(merchant_id: int, product_id: int, filename: str, content: bytes) -> str:
    """保存主图到 static/uploads 并写回商品，返回可访问 URL。"""
    get_product(merchant_id, product_id)
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise MerchantError("只支持 png/jpg/jpeg/webp/gif 图片")
    if not content:
        raise MerchantError("文件为空")
    if len(content) > MAX_IMAGE_BYTES:
        raise MerchantError("图片不能超过 5MB")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"p{product_id}_{uuid.uuid4().hex[:10]}{ext}"
    (UPLOAD_DIR / safe_name).write_bytes(content)
    url = f"{UPLOAD_URL_PREFIX}/{safe_name}"
    update_product(merchant_id, product_id, {"main_image": url})
    return url


def delete_image(merchant_id: int, product_id: int) -> None:
    """清空主图（回退到 CSS 兜底海报）。文件本身保留，避免误删历史引用。"""
    update_product(merchant_id, product_id, {"main_image": ""})


# ============ 数据看板 ============

def dashboard(merchant_id: int, days: int = 30) -> dict:
    """商家概览：商品数、营销位覆盖、埋点漏斗、Top 商品。"""
    days = min(365, max(1, int(days or 30)))
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(is_on_sale=1) AS on_sale, "
                "SUM(promo_banner<>'') AS with_promo, "
                "SUM(main_image<>'') AS with_image, "
                "AVG(price) AS avg_price "
                "FROM products WHERE merchant_id=%s",
                (merchant_id,),
            )
            overview = cur.fetchone() or {}

            cur.execute(
                "SELECT event_type, COUNT(*) AS n FROM product_events "
                "WHERE merchant_id=%s AND created_at >= NOW() - INTERVAL %s DAY "
                "GROUP BY event_type",
                (merchant_id, days),
            )
            funnel = {r["event_type"]: r["n"] for r in cur.fetchall()}

            cur.execute(
                "SELECT e.product_id, p.title, p.main_image, "
                "SUM(e.event_type='recommend') AS recommend_n, "
                "SUM(e.event_type='view') AS view_n, "
                "SUM(e.event_type='cart') AS cart_n, "
                "SUM(e.event_type='order') AS order_n, "
                "COUNT(*) AS total_n "
                "FROM product_events e JOIN products p ON p.id = e.product_id "
                "WHERE e.merchant_id=%s AND e.created_at >= NOW() - INTERVAL %s DAY "
                "GROUP BY e.product_id, p.title, p.main_image "
                "ORDER BY total_n DESC LIMIT 10",
                (merchant_id, days),
            )
            top = cur.fetchall()

            cur.execute(
                "SELECT DATE(created_at) AS d, COUNT(*) AS n FROM product_events "
                "WHERE merchant_id=%s AND created_at >= NOW() - INTERVAL %s DAY "
                "GROUP BY DATE(created_at) ORDER BY d",
                (merchant_id, days),
            )
            trend = [{"date": r["d"].strftime("%Y-%m-%d"), "count": r["n"]} for r in cur.fetchall()]
    finally:
        conn.close()

    total = int(overview.get("total") or 0)
    recommend_n = int(funnel.get("recommend", 0))
    cart_n = int(funnel.get("cart", 0))
    order_n = int(funnel.get("order", 0))
    return {
        "overview": {
            "total": total,
            "on_sale": int(overview.get("on_sale") or 0),
            "with_promo": int(overview.get("with_promo") or 0),
            "with_image": int(overview.get("with_image") or 0),
            "avg_price": round(float(overview.get("avg_price") or 0), 2),
        },
        "funnel": {
            "recommend": recommend_n,
            "view": int(funnel.get("view", 0)),
            "cart": cart_n,
            "order": order_n,
            # 转化率：加购/曝光、下单/加购
            "cart_rate": round(cart_n / recommend_n * 100, 1) if recommend_n else 0.0,
            "order_rate": round(order_n / cart_n * 100, 1) if cart_n else 0.0,
        },
        "top_products": [
            {
                "product_id": r["product_id"],
                "title": r["title"],
                "main_image": r["main_image"] or "",
                "recommend": int(r["recommend_n"]),
                "view": int(r["view_n"]),
                "cart": int(r["cart_n"]),
                "order": int(r["order_n"]),
            }
            for r in top
        ],
        "trend": trend,
        "days": days,
    }
