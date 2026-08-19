"""收藏服务（按用户隔离）。"""
import json

import pymysql

from app.core.config import settings
from app.services import catalog


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def add(user_id: int, product_id: int) -> list[dict]:
    if catalog.find_by_id(product_id) is None:
        raise ValueError(f"商品 {product_id} 不存在")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO favorites (user_id, product_id) VALUES (%s, %s)",
                (user_id, product_id),
            )
        conn.commit()
    finally:
        conn.close()
    return list_favorites(user_id)


def remove(user_id: int, product_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM favorites WHERE user_id=%s AND product_id=%s", (user_id, product_id))
        conn.commit()
    finally:
        conn.close()
    return list_favorites(user_id)


def list_favorites(user_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.title, p.brand, p.category, p.price, p.attributes, f.created_at, "
                "p.main_image, p.poster_bg, p.poster_headline, p.final_price, p.saved_amount, "
                "p.promo_banner, p.promo_banner_style, p.title_prefix, p.installment, "
                "p.service_tags, p.shop_name "
                "FROM favorites f JOIN products p ON f.product_id = p.id "
                "WHERE f.user_id=%s ORDER BY f.created_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        attrs = r["attributes"]
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except json.JSONDecodeError:
                attrs = {}
        tags = r.get("service_tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        out.append({
            "id": r["id"],
            "title": r["title"],
            "brand": r["brand"],
            "category": r["category"],
            "price": float(r["price"]),
            "attributes": attrs or {},
            "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "",
            # 营销位（收藏浮层与收藏页展示用）
            "main_image": r.get("main_image") or "",
            "poster_bg": r.get("poster_bg") or "",
            "poster_headline": r.get("poster_headline") or "",
            "final_price": float(r["final_price"]) if r.get("final_price") is not None else float(r["price"]),
            "saved_amount": float(r["saved_amount"]) if r.get("saved_amount") is not None else 0.0,
            "promo_banner": r.get("promo_banner") or "",
            "promo_banner_style": r.get("promo_banner_style") or "none",
            "title_prefix": r.get("title_prefix") or "",
            "installment": r.get("installment") or "",
            "service_tags": tags or [],
            "shop_name": r.get("shop_name") or "",
        })
    return out


def is_favorite(user_id: int, product_id: int) -> bool:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM favorites WHERE user_id=%s AND product_id=%s", (user_id, product_id))
            return cur.fetchone() is not None
    finally:
        conn.close()
