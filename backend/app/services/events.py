"""商品埋点：曝光 / 浏览 / 加购 / 下单。

写入 product_events 表，供商家数据看板聚合。
埋点属于旁路逻辑，任何异常都不应影响主流程，因此统一吞掉异常。
"""
import pymysql

from app.core.config import settings
from app.services import catalog

EVENT_TYPES = ("recommend", "view", "cart", "order")


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def track(product_ids, event_type: str, user_id: int | None = None, session_key: str = "") -> None:
    """记录一批商品的事件。product_ids 可以是单个 id 或可迭代对象。"""
    if event_type not in EVENT_TYPES:
        return
    if isinstance(product_ids, (int, str)):
        product_ids = [product_ids]
    rows = []
    for pid in product_ids:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        product = catalog.find_by_id(pid)
        rows.append((pid, (product or {}).get("merchant_id"), user_id, event_type, session_key or ""))
    if not rows:
        return
    try:
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO product_events (product_id, merchant_id, user_id, event_type, session_key) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    rows,
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # 埋点失败不影响业务主流程
        pass
