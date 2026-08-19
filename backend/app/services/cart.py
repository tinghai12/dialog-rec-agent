"""购物车 / 订单 / 用户画像服务（按用户隔离）。

- 购物车、订单、画像全部按 user_id 隔离（登录用户）
- 画像：聚合该用户所有历史会话的槽位，生成全局偏好标签与雷达图
"""
import json
import uuid
from datetime import datetime

import pymysql

from app.core.config import settings
from app.services import catalog, session_store


class CartError(Exception):
    pass


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


# ============ 购物车 ============

def add_to_cart(user_id: int, product_id: int) -> list[dict]:
    """加购（幂等）。返回购物车。"""
    if catalog.find_by_id(product_id) is None:
        raise CartError(f"商品 {product_id} 不存在")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, 1) "
                "ON DUPLICATE KEY UPDATE quantity = quantity + 1",
                (user_id, product_id),
            )
        conn.commit()
        return get_cart(user_id)
    finally:
        conn.close()


def get_cart(user_id: int) -> list[dict]:
    """返回购物车列表（join 商品全字段）。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id as item_id, c.product_id, c.quantity, p.title, p.brand, p.category, p.price, p.attributes "
                "FROM cart_items c JOIN products p ON c.product_id = p.id "
                "WHERE c.user_id = %s ORDER BY c.created_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        attrs = r["attributes"]
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except json.JSONDecodeError:
                attrs = {}
        items.append({
            "item_id": r["item_id"],
            "product_id": r["product_id"],
            "quantity": r["quantity"],
            "title": r["title"],
            "brand": r["brand"],
            "category": r["category"],
            "price": float(r["price"]),
            "attributes": attrs or {},
        })
    return items


def remove_cart_item(user_id: int, item_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cart_items WHERE id=%s AND user_id=%s", (item_id, user_id))
        conn.commit()
    finally:
        conn.close()
    return get_cart(user_id)


# ============ 订单 ============

def create_order(user_id: int) -> dict:
    """购物车 → 订单（人在环路确认后调用）。"""
    cart = get_cart(user_id)
    if not cart:
        raise CartError("购物车为空")
    total = round(sum(c["price"] * c["quantity"] for c in cart), 2)
    snapshot = [{"id": c["product_id"], "title": c["title"], "price": c["price"], "quantity": c["quantity"]} for c in cart]
    order_no = "D" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (order_no, user_id, products, total_amount, status) VALUES (%s, %s, %s, %s, 'pending')",
                (order_no, user_id, json.dumps(snapshot, ensure_ascii=False), total),
            )
            cur.execute("DELETE FROM cart_items WHERE user_id=%s", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return {"order_no": order_no, "products": snapshot, "total_amount": total, "status": "pending"}


def get_orders(user_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT order_no, products, total_amount, status, created_at FROM orders "
                "WHERE user_id=%s ORDER BY created_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        products = r["products"]
        if isinstance(products, str):
            try:
                products = json.loads(products)
            except json.JSONDecodeError:
                products = []
        out.append({
            "order_no": r["order_no"],
            "products": products,
            "total_amount": float(r["total_amount"]),
            "status": r["status"],
            "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "",
        })
    return out


# ============ 用户画像（聚合该用户所有会话） ============

def _slots_tags_radar(slots) -> tuple[list[str], dict]:
    tags = []
    radar = {
        "用途聚焦": 40, "预算明确": 40, "性能偏好": 40,
        "便携偏好": 40, "价格敏感": 40,
    }
    use_case = slots.get("use_case")
    if use_case:
        tags.append(f"用途：{use_case}")
        radar["用途聚焦"] = 80
        if use_case in ("写代码", "游戏", "剪辑"):
            radar["性能偏好"] = 85
    bmin, bmax = slots.get("budget_min"), slots.get("budget_max")
    if bmin is not None or bmax is not None:
        lo = int(round(bmin or 0))
        hi = int(round(bmax)) if bmax is not None else "不限"
        tags.append(f"预算：{lo}~{hi}")
        radar["预算明确"] = 85
        radar["价格敏感"] = 75
    for k, v in (slots.get("params") or {}).items():
        tags.append(f"{k}：{v}")
        if k in ("内存", "CPU", "显卡"):
            radar["性能偏好"] = max(radar["性能偏好"], 90)
        if k in ("重量", "电池", "续航"):
            radar["便携偏好"] = max(radar["便携偏好"], 85)
    if slots.get("brand"):
        tags.append(f"品牌：{slots['brand']}")
    if slots.get("exclude"):
        tags.append("排除：" + "、".join(slots["exclude"]))
    return tags, radar


def build_profile(user_id: int) -> dict:
    """聚合该用户所有历史会话的槽位，生成全局画像（标签去重合并，雷达图取最大值）。"""
    all_tags: list[str] = []
    radar = {"用途聚焦": 40, "预算明确": 40, "性能偏好": 40, "便携偏好": 40, "价格敏感": 40}

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM sessions WHERE user_id=%s", (user_id,))
            rows = cur.fetchall()
    finally:
        conn.close()

    for r in rows:
        state = r["state"]
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except json.JSONDecodeError:
                continue
        if not state:
            continue
        tags, sradar = _slots_tags_radar(state.get("slots") or {})
        for t in tags:
            if t not in all_tags:
                all_tags.append(t)
        for k in radar:
            radar[k] = max(radar[k], sradar[k])

    if not all_tags:
        all_tags = ["偏好待完善"]

    return {"user_id": user_id, "tags": all_tags, "radar": radar}
