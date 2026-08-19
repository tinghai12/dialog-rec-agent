"""把标准 products.json 导入 MySQL products 表。

用法（项目根目录）：
    python scripts/import_products.py
"""
import json
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import settings  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "products.json"


def main():
    products = json.loads(DATA.read_text(encoding="utf-8"))
    conn = pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
    )
    cur = conn.cursor()
    # 清空重建（幂等）
    cur.execute("DELETE FROM products")
    sql = (
        "INSERT INTO products (id, title, brand, category, price, attributes, pros, cons, reviews, is_on_sale) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1) "
        "ON DUPLICATE KEY UPDATE title=VALUES(title)"
    )
    for p in products:
        cur.execute(sql, (
            p["id"], p["title"], p["brand"], p["category"], float(p["price"]),
            json.dumps(p.get("attributes", {}), ensure_ascii=False),
            json.dumps(p.get("pros", []), ensure_ascii=False),
            json.dumps(p.get("cons", []), ensure_ascii=False),
            json.dumps(p.get("reviews", []), ensure_ascii=False),
        ))
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM products")
    print(f"导入完成: {cur.fetchone()[0]} 款商品 -> MySQL products 表")
    conn.close()


if __name__ == "__main__":
    main()
