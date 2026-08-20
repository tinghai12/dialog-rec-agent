"""订单服务：下单 / 查询 / 商家接单 / 配送进度。

状态流转：
    pending    下单成功，等商家接单
    shipping   商家已接单并发货，骑手配送中（用户端此时才显示配送轨迹）
    delivered  已送达
    cancelled  商家拒单

配送进度由后端按 shipped_at + eta_minutes 实时算出，前端只做两帧之间的插值动画，
因此刷新页面、换设备看到的进度都是连续的。
"""
import hashlib
import json
import math
import uuid
from datetime import datetime

import pymysql

from app.core.config import settings
from app.services import address as address_svc, catalog

# 骑手池：按订单号稳定选取，保证同一订单每次看到的骑手一致
_RIDERS = [
    ("王师傅", "138****2043"), ("李晓东", "139****7712"), ("赵鹏", "137****5589"),
    ("陈国庆", "136****3320"), ("刘洋", "135****9061"), ("孙明", "159****4477"),
]

STATUS_TEXT = {
    "pending": "待商家接单",
    "shipping": "配送中",
    "delivered": "已送达",
    "cancelled": "商家已拒单",
}

AFTERSALE_TEXT = {
    "none": "",
    "pending": "售后处理中",
    "approved": "售后已通过",
    "rejected": "售后被拒绝",
}

AFTERSALE_TYPES = {
    "refund": "仅退款",
    "return": "退货退款",
    "exchange": "换货",
    "repair": "维修",
}


class OrderError(Exception):
    pass


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _seed(order_no: str) -> int:
    """由订单号导出稳定随机种子，保证发货点/骑手/时长不会每次刷新都变。"""
    return int(hashlib.md5(order_no.encode("utf-8")).hexdigest()[:8], 16)


def _origin_from_dest(order_no: str, lng: float, lat: float) -> tuple[float, float]:
    """按订单号在收货点周边 3~7km 生成一个前置仓点（同城配送，轨迹动画才有观感）。"""
    seed = _seed(order_no)
    angle = (seed % 360) * math.pi / 180
    km = 3 + (seed // 360) % 5           # 3~7 km
    dlat = km / 111.0 * math.cos(angle)
    dlng = km / (111.0 * math.cos(math.radians(lat))) * math.sin(angle)
    return round(lng + dlng, 6), round(lat + dlat, 6)


def _distance_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """两点球面距离（km）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# 超过这个距离就不用商家总仓发货，改走同城前置仓（否则轨迹是几百公里的跨城长途）
_SAME_CITY_KM = 60


def _warehouse(cur, merchant_id: int | None) -> dict | None:
    if merchant_id is None:
        return None
    cur.execute(
        "SELECT warehouse_name, warehouse_address, warehouse_lng, warehouse_lat "
        "FROM users WHERE id=%s", (merchant_id,),
    )
    row = cur.fetchone()
    if not row or row["warehouse_lng"] is None:
        return None
    return {
        "name": row["warehouse_name"] or "商家仓库",
        "address": row["warehouse_address"] or "",
        "lng": float(row["warehouse_lng"]),
        "lat": float(row["warehouse_lat"]),
    }


def _pick_origin(cur, order_no: str, merchant_id: int | None,
                 dest_lng: float | None, dest_lat: float | None) -> tuple[float | None, float | None, str]:
    """选发货点：同城用商家仓库，跨城退回该城市的前置仓。"""
    if dest_lng is None or dest_lat is None:
        return None, None, ""
    wh = _warehouse(cur, merchant_id)
    if wh and _distance_km(wh["lng"], wh["lat"], dest_lng, dest_lat) <= _SAME_CITY_KM:
        return wh["lng"], wh["lat"], wh["name"]
    lng, lat = _origin_from_dest(order_no, dest_lng, dest_lat)
    name = f"{wh['name'].rstrip('仓')}同城前置仓" if wh else "同城前置仓"
    return lng, lat, name


# ============ 下单 ============

def create_order(user_id: int, address_id: int | None = None, session_key: str = "") -> list[dict]:
    """购物车 → 订单（按商家拆单，一个商家一个订单）。返回生成的订单列表。"""
    from app.services import cart as cart_svc

    items = cart_svc.get_cart(user_id)
    if not items:
        raise OrderError("购物车为空")

    addr = address_svc.get(user_id, address_id) if address_id else address_svc.get_default(user_id)
    if not addr:
        raise OrderError("请先添加收货地址")

    # 按商家分组
    groups: dict[int | None, list[dict]] = {}
    for it in items:
        product = catalog.find_by_id(it["product_id"]) or {}
        groups.setdefault(product.get("merchant_id"), []).append({**it, "_product": product})

    created = []
    conn = _conn()
    try:
        with conn.cursor() as cur:
            for merchant_id, group in groups.items():
                order_no = "D" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()
                seed = _seed(order_no)
                snapshot = [
                    {"id": c["product_id"], "title": c["title"], "price": c["price"],
                     "quantity": c["quantity"], "main_image": (c["_product"] or {}).get("main_image", ""),
                     "brand": c["brand"], "poster_bg": (c["_product"] or {}).get("poster_bg", ""),
                     "poster_headline": (c["_product"] or {}).get("poster_headline", "")}
                    for c in group
                ]
                total = round(sum(c["price"] * c["quantity"] for c in group), 2)
                shop_name = (group[0]["_product"] or {}).get("shop_name") or group[0]["brand"]
                rider = _RIDERS[seed % len(_RIDERS)]
                eta = 20 + seed % 25                      # 20~44 分钟
                dest_lng, dest_lat = addr["lng"], addr["lat"]
                origin_lng, origin_lat, origin_name = _pick_origin(
                    cur, order_no, merchant_id, dest_lng, dest_lat)

                cur.execute(
                    "INSERT INTO orders (order_no, user_id, merchant_id, shop_name, session_key, products, "
                    "total_amount, status, address_id, receiver, phone, address_text, dest_lng, dest_lat, "
                    "origin_lng, origin_lat, origin_name, eta_minutes, rider_name, rider_phone) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (order_no, user_id, merchant_id, shop_name, session_key,
                     json.dumps(snapshot, ensure_ascii=False), total, addr["id"], addr["receiver"],
                     addr["phone"], addr["full_text"], dest_lng, dest_lat,
                     origin_lng, origin_lat, origin_name, eta, rider[0], rider[1]),
                )
                created.append(order_no)
            cur.execute("DELETE FROM cart_items WHERE user_id=%s", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return [get_order(user_id, no) for no in created]


# ============ 查询 ============

def _row_out(row: dict, viewer: str = "buyer") -> dict:
    products = row.get("products")
    if isinstance(products, str):
        try:
            products = json.loads(products)
        except json.JSONDecodeError:
            products = []
    route = row.get("route")
    if isinstance(route, str):
        try:
            route = json.loads(route)
        except json.JSONDecodeError:
            route = None

    out = {
        "order_no": row["order_no"],
        "status": row["status"],
        "status_text": STATUS_TEXT.get(row["status"], row["status"]),
        "products": products or [],
        "total_amount": float(row["total_amount"]),
        "shop_name": row.get("shop_name") or "",
        "receiver": row.get("receiver") or "",
        "phone": row.get("phone") or "",
        "address_text": row.get("address_text") or "",
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M") if row.get("created_at") else "",
        "aftersale_status": row.get("aftersale_status") or "none",
        "aftersale_status_text": AFTERSALE_TEXT.get(row.get("aftersale_status") or "none", ""),
        "aftersale_type": row.get("aftersale_type") or "",
        "aftersale_type_text": AFTERSALE_TYPES.get(row.get("aftersale_type") or "", ""),
        "aftersale_reason": row.get("aftersale_reason") or "",
        "aftersale_reply": row.get("aftersale_reply") or "",
        "eta_minutes": int(row.get("eta_minutes") or 30),
        "rider_name": row.get("rider_name") or "",
        "rider_phone": row.get("rider_phone") or "",
        "has_route": bool(route),
        "origin": [float(row["origin_lng"]), float(row["origin_lat"])] if row.get("origin_lng") is not None else None,
        "origin_name": row.get("origin_name") or "",
        "warehouse_id": row.get("warehouse_id"),
        "dest": [float(row["dest_lng"]), float(row["dest_lat"])] if row.get("dest_lng") is not None else None,
    }
    if viewer == "buyer":
        out["route"] = route or []
    # 配送进度
    out.update(_delivery_state(row))
    return out


def _delivery_state(row: dict) -> dict:
    """按发货时间算配送进度（0~1）与剩余分钟数。"""
    if row["status"] != "shipping" or not row.get("shipped_at"):
        done = row["status"] == "delivered"
        return {"progress": 1.0 if done else 0.0, "remain_minutes": 0, "delivering": False}
    eta = max(1, int(row.get("eta_minutes") or 30))
    elapsed = (datetime.now() - row["shipped_at"]).total_seconds() / 60
    progress = min(1.0, max(0.0, elapsed / eta))
    return {
        "progress": round(progress, 4),
        "remain_minutes": max(0, math.ceil(eta - elapsed)),
        "delivering": progress < 1.0,
    }


def _finish_arrived(rows: list[dict]) -> None:
    """进度跑满的订单落库成已送达，避免每次都要重算。"""
    arrived = [r["order_no"] for r in rows
               if r["status"] == "shipping" and _delivery_state(r)["progress"] >= 1.0]
    if not arrived:
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE orders SET status='delivered', delivered_at=NOW() WHERE order_no=%s AND status='shipping'",
                [(no,) for no in arrived],
            )
        conn.commit()
    finally:
        conn.close()
    for r in rows:
        if r["order_no"] in arrived:
            r["status"] = "delivered"


def list_orders(user_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC", (user_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    _finish_arrived(rows)
    return [_row_out(r) for r in rows]


def get_order(user_id: int, order_no: str) -> dict:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE order_no=%s", (order_no,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise OrderError("订单不存在")
    if row["user_id"] != user_id:
        raise OrderError("无权查看该订单")
    _finish_arrived([row])
    return _row_out(row)


def save_route(user_id: int, order_no: str, route: list) -> int:
    """保存前端高德路径规划出的道路点，之后复用不再重复规划。"""
    get_order(user_id, order_no)
    points = [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in route if len(p) >= 2][:2000]
    if len(points) < 2:
        raise OrderError("路线点不足")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET route=%s WHERE order_no=%s AND user_id=%s",
                        (json.dumps(points), order_no, user_id))
        conn.commit()
    finally:
        conn.close()
    return len(points)


# ============ 商家侧 ============

def merchant_orders(merchant_id: int, status: str = "") -> list[dict]:
    where = ["merchant_id=%s"]
    params: list = [merchant_id]
    if status:
        where.append("status=%s")
        params.append(status)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM orders WHERE {' AND '.join(where)} "
                "ORDER BY FIELD(status,'pending','shipping','delivered','cancelled'), created_at DESC LIMIT 200",
                params,
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    _finish_arrived(rows)
    return [_row_out(r, viewer="merchant") for r in rows]


def pending_count(merchant_id: int) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM orders WHERE merchant_id=%s AND status='pending'", (merchant_id,))
            return cur.fetchone()["n"]
    finally:
        conn.close()


def _merchant_order(cur, merchant_id: int, order_no: str) -> dict:
    cur.execute("SELECT * FROM orders WHERE order_no=%s", (order_no,))
    row = cur.fetchone()
    if not row:
        raise OrderError("订单不存在")
    if row["merchant_id"] != merchant_id:
        raise OrderError("无权操作该订单")
    return row


def accept_order(merchant_id: int, order_no: str, warehouse_id: int | None = None) -> dict:
    """商家接单：选仓发货，扣减该仓库存，订单立刻进入配送。

    不传 warehouse_id 时用推荐仓（库存满足且最近）。
    """
    options = warehouse_options(merchant_id, order_no)
    if warehouse_id is None:
        warehouse_id = options.get("recommended_id")
    picked = next((w for w in options["warehouses"] if w["id"] == warehouse_id), None)

    conn = _conn()
    try:
        with conn.cursor() as cur:
            row = _merchant_order(cur, merchant_id, order_no)
            if row["status"] != "pending":
                raise OrderError(f"订单当前状态为「{STATUS_TEXT.get(row['status'], row['status'])}」，无法接单")

            if picked is None:
                # 商家还没建仓库：退回原有的同城前置仓逻辑，保证流程能走通
                cur.execute(
                    "UPDATE orders SET status='shipping', confirmed_at=NOW(), shipped_at=NOW() WHERE order_no=%s",
                    (order_no,),
                )
            else:
                if not picked["enough"]:
                    raise OrderError(f"「{picked['name']}」库存不足：" + _option_reason(picked, options["warehouses"]))
                need = {i["product_id"]: i["need"] for i in picked["items"]}
                _deduct_stock(cur, picked["id"], need)
                eta = _eta_for(picked.get("distance_km"), row.get("eta_minutes"))
                cur.execute(
                    "UPDATE orders SET status='shipping', confirmed_at=NOW(), shipped_at=NOW(), "
                    "warehouse_id=%s, origin_lng=%s, origin_lat=%s, origin_name=%s, eta_minutes=%s, route=NULL "
                    "WHERE order_no=%s",
                    (picked["id"], picked["lng"], picked["lat"], picked["name"], eta, order_no),
                )
        conn.commit()
    finally:
        conn.close()
    return _one_for_merchant(merchant_id, order_no)


def _eta_for(distance_km: float | None, fallback: int | None) -> int:
    """按仓库距离估配送时长：25km/h 均速 + 8 分钟出库备货。"""
    if distance_km is None:
        return int(fallback or 30)
    return max(8, min(180, round(distance_km / 25 * 60) + 8))


# ============ 售后 ============

def apply_aftersale(user_id: int, order_no: str, kind: str = "refund", reason: str = "") -> dict:
    """买家申请售后。已送达或配送中的订单可申请，等商家处理。"""
    if kind not in AFTERSALE_TYPES:
        kind = "refund"
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE order_no=%s", (order_no,))
            row = cur.fetchone()
            if not row:
                raise OrderError("订单不存在")
            if row["user_id"] != user_id:
                raise OrderError("无权操作该订单")
            if row["status"] in ("pending", "cancelled"):
                raise OrderError("该订单还没发货，可以直接联系商家取消，不需要申请售后")
            if row["aftersale_status"] == "pending":
                raise OrderError("这笔订单的售后正在处理中，请等商家响应")
            if row["aftersale_status"] == "approved":
                raise OrderError("这笔订单的售后已经通过了")
            cur.execute(
                "UPDATE orders SET aftersale_status='pending', aftersale_type=%s, "
                "aftersale_reason=%s, aftersale_reply='', aftersale_at=NOW() WHERE order_no=%s",
                (kind, (reason or "")[:255], order_no),
            )
        conn.commit()
    finally:
        conn.close()
    return get_order(user_id, order_no)


def aftersale_orders(merchant_id: int) -> list[dict]:
    """商家侧：等待处理的售后单。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM orders WHERE merchant_id=%s AND aftersale_status='pending' "
                "ORDER BY aftersale_at DESC",
                (merchant_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_row_out(r, viewer="merchant") for r in rows]


def aftersale_count(merchant_id: int) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE merchant_id=%s AND aftersale_status='pending'",
                (merchant_id,),
            )
            return cur.fetchone()["n"]
    finally:
        conn.close()


def handle_aftersale(merchant_id: int, order_no: str, approve: bool, reply: str = "") -> dict:
    """商家处理售后：同意或拒绝。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            row = _merchant_order(cur, merchant_id, order_no)
            if row["aftersale_status"] != "pending":
                raise OrderError("该订单没有待处理的售后申请")
            cur.execute(
                "UPDATE orders SET aftersale_status=%s, aftersale_reply=%s WHERE order_no=%s",
                ("approved" if approve else "rejected", (reply or "")[:255], order_no),
            )
        conn.commit()
    finally:
        conn.close()
    return _one_for_merchant(merchant_id, order_no)


def reject_order(merchant_id: int, order_no: str) -> dict:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            row = _merchant_order(cur, merchant_id, order_no)
            if row["status"] != "pending":
                raise OrderError("只有待接单的订单可以拒单")
            cur.execute("UPDATE orders SET status='cancelled' WHERE order_no=%s", (order_no,))
        conn.commit()
    finally:
        conn.close()
    return _one_for_merchant(merchant_id, order_no)


def _one_for_merchant(merchant_id: int, order_no: str) -> dict:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            row = _merchant_order(cur, merchant_id, order_no)
    finally:
        conn.close()
    return _row_out(row, viewer="merchant")


# ============ 选仓发货 ============

def warehouse_options(merchant_id: int, order_no: str) -> dict:
    """列出该订单可选的发货仓：到收货地址的距离 + 每个商品在该仓的剩余量。

    推荐规则：库存全部满足的仓里选最近的；没有全满足的，选缺口最小、其次最近的。
    """
    conn = _conn()
    try:
        with conn.cursor() as cur:
            row = _merchant_order(cur, merchant_id, order_no)
            products = row.get("products")
            if isinstance(products, str):
                products = json.loads(products)
            products = products or []
            need = {int(p["id"]): int(p.get("quantity") or 1) for p in products}
            titles = {int(p["id"]): p.get("title", "") for p in products}

            cur.execute(
                "SELECT id, name, address, lng, lat, is_default FROM warehouses "
                "WHERE merchant_id=%s ORDER BY is_default DESC, id",
                (merchant_id,),
            )
            warehouses = cur.fetchall()
            if not warehouses:
                return {"order_no": order_no, "warehouses": [], "recommended_id": None}

            cur.execute(
                "SELECT warehouse_id, product_id, quantity FROM warehouse_stock "
                "WHERE warehouse_id IN %s AND product_id IN %s",
                ([w["id"] for w in warehouses], list(need.keys()) or [0]),
            )
            stock = {(r["warehouse_id"], r["product_id"]): r["quantity"] for r in cur.fetchall()}
    finally:
        conn.close()

    dest_lng = float(row["dest_lng"]) if row.get("dest_lng") is not None else None
    dest_lat = float(row["dest_lat"]) if row.get("dest_lat") is not None else None

    options = []
    for w in warehouses:
        items, shortage = [], 0
        for pid, qty in need.items():
            have = int(stock.get((w["id"], pid), 0))
            lack = max(0, qty - have)
            shortage += lack
            items.append({
                "product_id": pid, "title": titles.get(pid, ""),
                "need": qty, "stock": have, "enough": lack == 0,
            })
        distance = None
        if dest_lng is not None and w["lng"] is not None:
            distance = round(_distance_km(float(w["lng"]), float(w["lat"]), dest_lng, dest_lat), 1)
        options.append({
            "id": w["id"],
            "name": w["name"],
            "address": w["address"],
            "lng": float(w["lng"]) if w["lng"] is not None else None,
            "lat": float(w["lat"]) if w["lat"] is not None else None,
            "is_default": bool(w["is_default"]),
            "distance_km": distance,
            "items": items,
            "shortage": shortage,
            "enough": shortage == 0,
        })

    # 先按缺口升序，再按距离升序（距离缺失的排后面）
    ranked = sorted(options, key=lambda o: (o["shortage"], o["distance_km"] if o["distance_km"] is not None else 1e9))
    best = ranked[0] if ranked else None
    for o in options:
        o["recommended"] = bool(best and o["id"] == best["id"])
        o["reason"] = _option_reason(o, ranked)
    return {
        "order_no": order_no,
        "status": row["status"],
        "address_text": row.get("address_text") or "",
        "warehouses": options,
        "recommended_id": best["id"] if best else None,
    }


def _option_reason(option: dict, ranked: list[dict]) -> str:
    """给每个仓一句人话说明，商家端和 AI 订单助手都直接用。"""
    if not option["enough"]:
        lack = [i["title"][:12] for i in option["items"] if not i["enough"]]
        return f"缺货：{'、'.join(lack)}"
    if option.get("distance_km") is None:
        return "库存充足，但缺少坐标无法算距离"
    nearer = [o for o in ranked
              if o["enough"] and o["distance_km"] is not None and o["distance_km"] < option["distance_km"]]
    if not nearer:
        return f"库存充足且最近，距收货地址 {option['distance_km']}km"
    return f"库存充足，距收货地址 {option['distance_km']}km"


def _deduct_stock(cur, warehouse_id: int, need: dict[int, int]) -> None:
    """扣减库存；任一商品不足直接抛错（外层事务未提交，不会写脏）。"""
    for pid, qty in need.items():
        cur.execute(
            "UPDATE warehouse_stock SET quantity = quantity - %s "
            "WHERE warehouse_id=%s AND product_id=%s AND quantity >= %s",
            (qty, warehouse_id, pid, qty),
        )
        if cur.rowcount == 0:
            raise OrderError("该仓库存不足，请换一个仓库发货")
