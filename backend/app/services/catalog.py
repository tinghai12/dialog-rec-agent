"""商品目录。

数据源优先 MySQL products 表（含商家维护的营销位字段），
MySQL 不可用时回退到 backend/app/data/products.json（保证离线可跑）。

内存缓存一份，商家端写操作后调用 invalidate() 让下次读取重新加载。

提供 sql_filter：按槽位做结构化过滤（价格区间 / 品牌 / 排除项 / 配置参数数值比较）。
"""
import json
import re
from pathlib import Path

import pymysql

from app.core.config import settings

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

_products: list[dict] = []
_source: str = ""

# MySQL 中的营销位字段（商家端可编辑）
MARKETING_FIELDS = (
    "shop_name", "main_image", "poster_bg", "poster_headline", "poster_subline",
    "poster_specs", "poster_price_label", "promo_banner", "promo_banner_style",
    "title_prefix", "rank_label", "final_price", "saved_amount", "installment",
    "service_tags", "sold_count", "repeat_buyers",
)

_JSON_COLUMNS = ("attributes", "pros", "cons", "reviews", "poster_specs", "service_tags")


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _decode_json_columns(row: dict) -> dict:
    """MySQL 驱动可能把 JSON 列返回为字符串，统一解析成 Python 对象。"""
    for key in _JSON_COLUMNS:
        value = row.get(key)
        if isinstance(value, str):
            try:
                row[key] = json.loads(value)
            except json.JSONDecodeError:
                row[key] = None
    row["attributes"] = row.get("attributes") or {}
    for key in ("pros", "cons", "reviews", "poster_specs", "service_tags"):
        row[key] = row.get(key) or []
    return row


def _normalize(row: dict) -> dict:
    """统一类型：价格转 float，营销位补默认值。"""
    row = _decode_json_columns(dict(row))
    row["price"] = float(row["price"])
    for key in ("final_price", "saved_amount"):
        row[key] = float(row[key]) if row.get(key) is not None else None
    # 到手价缺省即原价，前端不必再判空
    if row.get("final_price") is None:
        row["final_price"] = row["price"]
    for key in ("poster_bg", "poster_headline", "poster_subline", "poster_price_label",
                "promo_banner", "title_prefix", "rank_label", "installment",
                "main_image", "shop_name"):
        row[key] = row.get(key) or ""
    row["promo_banner_style"] = row.get("promo_banner_style") or "none"
    row["sold_count"] = int(row.get("sold_count") or 0)
    row["repeat_buyers"] = int(row.get("repeat_buyers") or 0)
    row["is_on_sale"] = int(row.get("is_on_sale", 1))
    return row


def _load_from_mysql() -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, brand, category, price, attributes, pros, cons, reviews, "
                "is_on_sale, merchant_id, " + ", ".join(MARKETING_FIELDS) + " "
                "FROM products ORDER BY id"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_normalize(r) for r in rows]


def _load_from_json() -> list[dict]:
    with open(_DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for p in raw:
        row = dict(p)
        row.setdefault("merchant_id", None)
        for key in MARKETING_FIELDS:
            row.setdefault(key, None)
        out.append(_normalize(row))
    return out


def load() -> None:
    """加载商品：优先 MySQL，失败回退 JSON 文件。"""
    global _products, _source
    try:
        items = _load_from_mysql()
        if items:
            _products, _source = items, "mysql"
            return
    except Exception:
        pass
    _products, _source = _load_from_json(), "json"


def invalidate() -> None:
    """清空缓存（商家端增删改后调用）。"""
    global _products
    _products = []


def source() -> str:
    if not _products:
        load()
    return _source


def get_all() -> list[dict]:
    if not _products:
        load()
    return _products


def find_by_id(pid) -> dict | None:
    for p in get_all():
        if p["id"] == pid:
            return p
    return None


def _num(value) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else None


def _meets_param(product: dict, key: str, value: str) -> bool:
    """配置参数是否满足。内存/硬盘/电池 要求≥；重量 要求≤；其余做包含匹配。"""
    actual = (product.get("attributes") or {}).get(key)
    if actual is None:
        return False
    target = _num(value)
    real = _num(actual)
    if target is not None and real is not None:
        if key in ("内存", "硬盘", "电池"):
            return real >= target
        if key == "重量":
            return real <= target
    return str(value).lower() in str(actual).lower()


def sql_filter(slots) -> list[dict]:
    """按槽位过滤，返回满足硬约束的商品（不排序）。"""
    result = []
    for p in get_all():
        if not p.get("is_on_sale", 1):
            continue
        if slots.category and p["category"] != slots.category:
            continue
        price = float(p["price"])
        if slots.budget_min is not None and price < slots.budget_min:
            continue
        if slots.budget_max is not None and price > slots.budget_max:
            continue
        if slots.brand and slots.brand not in p["brand"]:
            continue
        if any(ex in p["brand"] or ex in p["title"] for ex in slots.exclude):
            continue
        if not all(_meets_param(p, k, v) for k, v in slots.params.items()):
            continue
        result.append(p)
    return result
