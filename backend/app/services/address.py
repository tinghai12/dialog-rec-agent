"""收货地址服务（按用户隔离）。

地址长期登记在 addresses 表，下单时快照进订单，之后改地址不影响历史订单。
经纬度由前端用高德地理编码换算后带上；没有坐标时下单会退化为按城市中心估算。
"""
import pymysql

from app.core.config import settings


class AddressError(Exception):
    pass


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _out(row: dict) -> dict:
    return {
        "id": row["id"],
        "receiver": row["receiver"],
        "phone": row["phone"],
        "province": row["province"],
        "city": row["city"],
        "district": row["district"],
        "detail": row["detail"],
        "lng": float(row["lng"]) if row.get("lng") is not None else None,
        "lat": float(row["lat"]) if row.get("lat") is not None else None,
        "is_default": bool(row["is_default"]),
        "full_text": "".join([row["province"], row["city"], row["district"], row["detail"]]),
    }


def list_addresses(user_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM addresses WHERE user_id=%s ORDER BY is_default DESC, updated_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_out(r) for r in rows]


def get_default(user_id: int) -> dict | None:
    items = list_addresses(user_id)
    return items[0] if items else None


def _validate(data: dict) -> dict:
    receiver = str(data.get("receiver") or "").strip()
    phone = str(data.get("phone") or "").strip()
    detail = str(data.get("detail") or "").strip()
    if not receiver:
        raise AddressError("收货人不能为空")
    if not phone:
        raise AddressError("联系电话不能为空")
    if not detail:
        raise AddressError("详细地址不能为空")
    return {
        "receiver": receiver[:50],
        "phone": phone[:20],
        "province": str(data.get("province") or "").strip()[:50],
        "city": str(data.get("city") or "").strip()[:50],
        "district": str(data.get("district") or "").strip()[:50],
        "detail": detail[:255],
        "lng": data.get("lng"),
        "lat": data.get("lat"),
    }


def _clear_default(cur, user_id: int) -> None:
    cur.execute("UPDATE addresses SET is_default=0 WHERE user_id=%s", (user_id,))


def create(user_id: int, data: dict) -> dict:
    fields = _validate(data)
    # 第一条地址自动成为默认地址
    make_default = bool(data.get("is_default")) or not list_addresses(user_id)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if make_default:
                _clear_default(cur, user_id)
            cur.execute(
                "INSERT INTO addresses (user_id, receiver, phone, province, city, district, detail, lng, lat, is_default) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (user_id, fields["receiver"], fields["phone"], fields["province"], fields["city"],
                 fields["district"], fields["detail"], fields["lng"], fields["lat"], 1 if make_default else 0),
            )
            new_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return get(user_id, new_id)


def get(user_id: int, address_id: int) -> dict:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM addresses WHERE id=%s", (address_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise AddressError("地址不存在")
    if row["user_id"] != user_id:
        raise AddressError("无权操作该地址")
    return _out(row)


def update(user_id: int, address_id: int, data: dict) -> dict:
    get(user_id, address_id)          # 校验归属
    fields = _validate(data)
    make_default = bool(data.get("is_default"))
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if make_default:
                _clear_default(cur, user_id)
            cur.execute(
                "UPDATE addresses SET receiver=%s, phone=%s, province=%s, city=%s, district=%s, "
                "detail=%s, lng=%s, lat=%s, is_default=%s WHERE id=%s AND user_id=%s",
                (fields["receiver"], fields["phone"], fields["province"], fields["city"],
                 fields["district"], fields["detail"], fields["lng"], fields["lat"],
                 1 if make_default else 0, address_id, user_id),
            )
        conn.commit()
    finally:
        conn.close()
    return get(user_id, address_id)


def set_default(user_id: int, address_id: int) -> dict:
    get(user_id, address_id)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            _clear_default(cur, user_id)
            cur.execute("UPDATE addresses SET is_default=1 WHERE id=%s AND user_id=%s", (address_id, user_id))
        conn.commit()
    finally:
        conn.close()
    return get(user_id, address_id)


def delete(user_id: int, address_id: int) -> None:
    addr = get(user_id, address_id)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM addresses WHERE id=%s AND user_id=%s", (address_id, user_id))
            # 删掉的是默认地址就把最近一条顶上去
            if addr["is_default"]:
                cur.execute(
                    "UPDATE addresses SET is_default=1 WHERE user_id=%s ORDER BY updated_at DESC LIMIT 1",
                    (user_id,),
                )
        conn.commit()
    finally:
        conn.close()
