"""text2sql:把自然语言需求翻译成 SQL 查询 MySQL。

这是"大模型工具调用"的落点：LLM 根据用户需求生成 SQL，执行后返回商品。
安全：只允许单条 SELECT，拒绝多语句/写入/注入。
降级：LLM 失败或 SQL 非法时抛异常，由上层回退到内存过滤。
"""
import json
import re

import pymysql

from app.core.config import settings
from app.services import llm


TEXT2SQL_SYSTEM = """你是数据库查询助手。把用户购物需求翻译成 MySQL 查询，目标是 products 表。

表结构：products(id BIGINT, title, brand, category, price DECIMAL, attributes JSON, is_on_sale TINYINT)
- category 取值：'笔记本' 或 '手机'
- attributes 是 JSON 字符串，常用键：内存/硬盘/重量/屏幕/CPU/显卡/电池/芯片/摄像头/续航
- 数值型参数（内存/硬盘/电池）用 JSON_UNQUOTE(JSON_EXTRACT(attributes,'$.内存')) 取出后 CAST 为 UNSIGNED 再比较
- 重量同理取 '$.重量'，用 <= 比较

要求：
1. 只输出一条 SELECT 语句，WHERE 覆盖用户全部硬约束（预算价格、品牌、品类、参数、排除品牌）。
2. 内存/硬盘/电池 用 >=，重量 用 <=，屏幕/CPU 用 LIKE 模糊匹配。
3. 排除品牌用 brand NOT IN (...) 或 title 不含。
4. 不要 LIMIT 超过 50；不强制 ORDER BY；只选需要的列（id,title,brand,category,price,attributes）。
5. 只输出 SQL 本身，不要 ``` 围栏、不要解释、不要注释。
"""


class Text2SQLError(Exception):
    pass


# SQL 缓存：同样的需求文本复用已生成的 SQL，省一次 LLM 调用
_sql_cache: dict[str, str] = {}


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def generate_sql(requirement: str) -> str:
    """LLM 生成 SQL。"""
    raw = llm._post(TEXT2SQL_SYSTEM, requirement, temperature=0.1, max_tokens=400).strip()
    raw = re.sub(r"^```(?:sql)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # 只允许单条 SELECT
    if not re.match(r"^\s*SELECT\b", raw, re.IGNORECASE):
        raise Text2SQLError(f"LLM 未生成 SELECT: {raw[:80]}")
    if ";" in raw.rstrip(";").rstrip() or ";" in raw[:-1]:
        # 只保留最后一个分号前的部分，拒绝多语句
        stmts = raw.split(";")
        if len([s for s in stmts if s.strip()]) > 1:
            raise Text2SQLError("检测到多语句 SQL，拒绝执行")
        raw = stmts[0]
    # 拒绝危险关键词
    for kw in ("DELETE", "DROP", "INSERT", "UPDATE", "ALTER", "CREATE", "GRANT", "INTO OUTFILE"):
        if re.search(rf"\b{kw}\b", raw, re.IGNORECASE):
            raise Text2SQLError(f"检测到危险关键词 {kw}")
    return raw


def query(sql: str) -> list[dict]:
    """执行 SQL，返回商品列表。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        attrs = r.get("attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except json.JSONDecodeError:
                attrs = {}
        out.append({
            "id": int(r["id"]),
            "title": r["title"],
            "brand": r["brand"],
            "category": r["category"],
            "price": float(r["price"]),
            "attributes": attrs or {},
        })
    return out


def search(requirement: str) -> list[dict]:
    """text2sql 完整流程：生成 SQL → 执行 → 返回商品。失败抛异常由上层降级。

    同样的需求文本命中缓存则跳过 LLM 调用（省 token）。
    """
    key = requirement.strip()
    sql = _sql_cache.get(key)
    if sql is None:
        sql = generate_sql(requirement)
        _sql_cache[key] = sql
    return query(sql)
