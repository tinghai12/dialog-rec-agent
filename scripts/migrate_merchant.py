"""商家体系迁移脚本（幂等，可重复执行）。

做四件事：
1. 给 users / products 补齐角色与营销位字段（已存在则跳过），建 product_events 表
2. 把 products.json 的 500 款商品导入 MySQL products 表
3. 按品牌创建商家账号（每个品牌一个店铺），并把该品牌商品绑到对应商家
4. 为商品生成默认营销位数据（基于 id 的确定性伪随机，重复执行结果一致）

用法（项目根目录）：
    python scripts/migrate_merchant.py

商家账号：merchant01 ~ merchantNN，密码统一 123456，店铺名 = "{品牌}官方旗舰店"
"""
import json
import sys
from pathlib import Path

import bcrypt
import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import settings  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "products.json"
DEFAULT_PASSWORD = "123456"

# ---- 需要补齐的列：{表: [(列名, DDL 片段), ...]} ----
COLUMNS = {
    "users": [
        ("role", "VARCHAR(20) NOT NULL DEFAULT 'buyer' COMMENT '角色: buyer/merchant'"),
        ("shop_name", "VARCHAR(100) NOT NULL DEFAULT '' COMMENT '店铺名'"),
    ],
    "messages": [
        ("cards", "JSON NULL COMMENT '该条回复附带的推荐卡片'"),
    ],
    "sessions": [
        ("pinned", "TINYINT NOT NULL DEFAULT 0 COMMENT '是否置顶 0/1'"),
    ],
    "products": [
        ("merchant_id", "BIGINT NULL COMMENT '所属商家 users.id'"),
        ("shop_name", "VARCHAR(100) NOT NULL DEFAULT '' COMMENT '店铺名(冗余)'"),
        ("main_image", "VARCHAR(255) NOT NULL DEFAULT '' COMMENT '主图URL'"),
        ("poster_bg", "VARCHAR(60) NOT NULL DEFAULT '' COMMENT '兜底海报底色主题'"),
        ("poster_headline", "VARCHAR(60) NOT NULL DEFAULT '' COMMENT '海报主标语'"),
        ("poster_subline", "VARCHAR(80) NOT NULL DEFAULT '' COMMENT '海报副标语'"),
        ("poster_specs", "JSON NULL COMMENT '海报规格浮层'"),
        ("poster_price_label", "VARCHAR(30) NOT NULL DEFAULT '' COMMENT '浮层价格前缀'"),
        ("promo_banner", "VARCHAR(60) NOT NULL DEFAULT '' COMMENT '促销条文案'"),
        ("promo_banner_style", "VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT '促销条样式'"),
        ("title_prefix", "VARCHAR(60) NOT NULL DEFAULT '' COMMENT '标题前缀优惠'"),
        ("rank_label", "VARCHAR(60) NOT NULL DEFAULT '' COMMENT '榜单标签'"),
        ("final_price", "DECIMAL(10,2) NULL COMMENT '到手价'"),
        ("saved_amount", "DECIMAL(10,2) NULL COMMENT '已省金额'"),
        ("installment", "VARCHAR(20) NOT NULL DEFAULT '' COMMENT '分期'"),
        ("service_tags", "JSON NULL COMMENT '服务标签'"),
        ("sold_count", "INT NOT NULL DEFAULT 0 COMMENT '付款人数'"),
        ("repeat_buyers", "INT NOT NULL DEFAULT 0 COMMENT '回头客人数'"),
        ("promo_start", "DATETIME NULL COMMENT '活动开始'"),
        ("promo_end", "DATETIME NULL COMMENT '活动结束'"),
    ],
}

INDEXES = [
    ("users", "idx_role", "ALTER TABLE users ADD KEY idx_role (role)"),
    ("products", "idx_merchant", "ALTER TABLE products ADD KEY idx_merchant (merchant_id)"),
]

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS product_events (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id    BIGINT        NOT NULL,
    merchant_id   BIGINT        NULL,
    user_id       BIGINT        NULL,
    event_type    VARCHAR(20)   NOT NULL COMMENT 'recommend/view/cart/order',
    session_key   VARCHAR(64)   NOT NULL DEFAULT '',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_merchant_type (merchant_id, event_type),
    KEY idx_product_type (product_id, event_type),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品埋点事件'
"""

# ---- 营销位素材池（按 id 轮换，保证确定性） ----
BANNERS = [
    ("天猫 七夕礼遇季", "tmall"),
    ("国家补贴立省15%", "subsidy"),
    ("直播间下单立减500元", "live"),
    ("天猫 超级品牌日", "tmall"),
    ("政府补贴15% 全国多地可用", "subsidy"),
]
HEADLINES = {
    "笔记本": [
        ("超强芯生 高效出众", "轻薄机身 全天续航"),
        ("性能怪兽 一战到底", "高刷电竞屏 冷静散热"),
        ("轻若无形 随行随创", "一整天不用找插座"),
        ("创作利器 色准出厂校准", "剪辑渲染快人一步"),
    ],
    "手机": [
        ("影像旗舰 一拍即封面", "大底主摄 夜景更干净"),
        ("续航猛兽 两天一充", "超级快充 十分钟满血"),
        ("性能满配 帧率稳如钉", "游戏久战不烫手"),
        ("轻薄手感 一握就顺", "高刷护眼屏 久看不累"),
    ],
}
PRICE_LABELS = ["国补到手价", "券后到手价", "限时到手价", "百亿补贴价"]
INSTALLMENTS = ["3期", "12期", "24期免息", "6期免息"]
TITLE_PREFIXES = ["【24期免息】", "【国家补贴15%】", "【优先顺丰】", "【直播间立减500元】", ""]
SERVICE_TAGS = [
    ["退货宝", "包邮"],
    ["退货宝"],
    ["包邮", "七天无理由"],
    ["退货宝", "闪电发货"],
]
POSTER_BGS = ["dark", "blue", "purple", "red", "green", "ink"]
RANK_LABELS = {
    "笔记本": ["办公笔记本好评榜·第1名", "入选DIY兼容机好评榜", "轻薄本热卖榜·第1名", ""],
    "手机": ["手机好评榜·第1名", "拍照手机热卖榜·第2名", "5G手机口碑榜·第1名", ""],
}
PROMO_START = "2026-08-04 00:00:00"
PROMO_END = "2026-08-31 23:59:59"


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _existing_columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (settings.MYSQL_DB, table),
    )
    return {r["COLUMN_NAME"] for r in cur.fetchall()}


def _index_exists(cur, table: str, index: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s LIMIT 1",
        (settings.MYSQL_DB, table, index),
    )
    return cur.fetchone() is not None


def step1_alter(cur) -> None:
    """补齐字段与索引、建埋点表。"""
    added = 0
    for table, cols in COLUMNS.items():
        have = _existing_columns(cur, table)
        if not have:
            print(f"  ! 表 {table} 不存在，请先执行 db/schema.sql")
            continue
        for name, ddl in cols:
            if name in have:
                continue
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            added += 1
            print(f"  + {table}.{name}")
    for table, index, sql in INDEXES:
        if _existing_columns(cur, table) and not _index_exists(cur, table, index):
            cur.execute(sql)
            print(f"  + index {table}.{index}")
    cur.execute(EVENTS_DDL)
    print(f"  字段补齐完成（新增 {added} 列），product_events 就绪")


def step2_import_products(cur) -> list[dict]:
    """导入商品（幂等：按 id UPSERT，不清表，避免丢掉商家已改的营销位）。"""
    products = json.loads(DATA.read_text(encoding="utf-8"))
    sql = (
        "INSERT INTO products (id, title, brand, category, price, attributes, pros, cons, reviews, is_on_sale) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1) "
        "ON DUPLICATE KEY UPDATE title=VALUES(title), brand=VALUES(brand), category=VALUES(category), "
        "price=VALUES(price), attributes=VALUES(attributes), pros=VALUES(pros), cons=VALUES(cons), reviews=VALUES(reviews)"
    )
    for p in products:
        cur.execute(sql, (
            p["id"], p["title"], p["brand"], p["category"], float(p["price"]),
            json.dumps(p.get("attributes", {}), ensure_ascii=False),
            json.dumps(p.get("pros", []), ensure_ascii=False),
            json.dumps(p.get("cons", []), ensure_ascii=False),
            json.dumps(p.get("reviews", []), ensure_ascii=False),
        ))
    cur.execute("SELECT COUNT(*) AS n FROM products")
    print(f"  商品导入完成，products 表共 {cur.fetchone()['n']} 款")
    return products


def step3_merchants(cur, products: list[dict]) -> dict[str, int]:
    """按品牌建商家账号，返回 {品牌: merchant_id}。"""
    brands = sorted({p["brand"] for p in products})
    pw_hash = bcrypt.hashpw(DEFAULT_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    brand_to_id: dict[str, int] = {}
    created = 0
    for i, brand in enumerate(brands, start=1):
        username = f"merchant{i:02d}"
        shop_name = f"{brand}官方旗舰店"
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        row = cur.fetchone()
        if row:
            # 已存在则只补角色/店铺名，不覆盖密码
            cur.execute(
                "UPDATE users SET role='merchant', shop_name=%s, nickname=%s WHERE id=%s",
                (shop_name, shop_name, row["id"]),
            )
            brand_to_id[brand] = row["id"]
            continue
        cur.execute(
            "INSERT INTO users (username, password_hash, nickname, role, shop_name) "
            "VALUES (%s, %s, %s, 'merchant', %s)",
            (username, pw_hash, shop_name, shop_name),
        )
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        brand_to_id[brand] = cur.fetchone()["id"]
        created += 1
    # 商品绑定商家
    for brand, mid in brand_to_id.items():
        cur.execute(
            "UPDATE products SET merchant_id=%s, shop_name=%s WHERE brand=%s",
            (mid, f"{brand}官方旗舰店", brand),
        )
    print(f"  商家账号 {len(brand_to_id)} 个（新建 {created}），商品归属已绑定")
    return brand_to_id


def _marketing_for(p: dict) -> dict:
    """基于商品 id 的确定性营销位数据。"""
    pid = int(p["id"])
    price = float(p["price"])
    category = p["category"]
    attrs = p.get("attributes") or {}

    banner, banner_style = BANNERS[pid % len(BANNERS)]
    headline, subline = HEADLINES.get(category, HEADLINES["笔记本"])[pid % 4]
    ranks = RANK_LABELS.get(category, RANK_LABELS["笔记本"])

    # 规格浮层：优先 CPU / 显卡，退化到 内存 / 硬盘
    specs = [attrs[k] for k in ("CPU", "显卡") if attrs.get(k)]
    if len(specs) < 2:
        specs = [attrs[k] for k in ("内存", "硬盘", "屏幕") if attrs.get(k)][:2]
    specs = [str(s) for s in specs[:2]]

    discount = 1 - (0.03 + (pid % 10) * 0.01)          # 3% ~ 12%
    final_price = round(price * discount, 2)
    saved = round(price - final_price, 2)

    return {
        "poster_bg": POSTER_BGS[pid % len(POSTER_BGS)],
        "poster_headline": headline,
        "poster_subline": subline,
        "poster_specs": json.dumps(specs, ensure_ascii=False),
        "poster_price_label": PRICE_LABELS[pid % len(PRICE_LABELS)],
        "promo_banner": banner,
        "promo_banner_style": banner_style,
        "title_prefix": TITLE_PREFIXES[pid % len(TITLE_PREFIXES)],
        "rank_label": ranks[pid % len(ranks)],
        "final_price": final_price,
        "saved_amount": saved,
        "installment": INSTALLMENTS[pid % len(INSTALLMENTS)],
        "service_tags": json.dumps(SERVICE_TAGS[pid % len(SERVICE_TAGS)], ensure_ascii=False),
        "sold_count": 100 + (pid * 137) % 9900,
        "repeat_buyers": 1000 + (pid * 971) % 99000,
        "promo_start": PROMO_START,
        "promo_end": PROMO_END,
    }


def step4_marketing(cur, products: list[dict], only_empty: bool = True) -> None:
    """填充营销位。only_empty=True 时只填从未设置过的商品（保护商家改动）。"""
    if only_empty:
        cur.execute("SELECT id FROM products WHERE promo_banner='' OR promo_banner IS NULL")
        todo = {r["id"] for r in cur.fetchall()}
    else:
        todo = {p["id"] for p in products}
    if not todo:
        print("  营销位已存在，跳过（加 --force 可强制重置）")
        return
    fields = list(_marketing_for(products[0]).keys())
    sql = f"UPDATE products SET {', '.join(f'{f}=%s' for f in fields)} WHERE id=%s"
    for p in products:
        if p["id"] not in todo:
            continue
        m = _marketing_for(p)
        cur.execute(sql, [m[f] for f in fields] + [p["id"]])
    print(f"  营销位填充 {len(todo)} 款商品")


def main() -> None:
    force = "--force" in sys.argv
    conn = _conn()
    try:
        with conn.cursor() as cur:
            print("[1/4] 补齐表结构")
            step1_alter(cur)
            conn.commit()

            print("[2/4] 导入商品")
            products = step2_import_products(cur)
            conn.commit()

            print("[3/4] 创建商家并绑定商品")
            step3_merchants(cur, products)
            conn.commit()

            print(f"[4/4] 填充营销位{'（强制重置）' if force else ''}")
            step4_marketing(cur, products, only_empty=not force)
            conn.commit()
    finally:
        conn.close()
    print(f"\n迁移完成。商家账号 merchant01 ~，密码 {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    main()
