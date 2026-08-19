"""自然语言商品搜索：输入一句话需求，返回匹配商品（不展开对话）。

流程：LLM 抽槽位 → 结构化过滤(text2sql/内存) + 向量检索 → 规则粗排 → Top-N
复用 orchestrator 的检索链，但只返回列表，不进入对话状态机。
"""
from app.core.config import settings
from app.services import catalog, llm, text2sql, vector_store
from app.services.session_store import SlotState


def _slot_text(s: SlotState) -> str:
    parts = []
    if s.category:
        parts.append(s.category)
    if s.use_case:
        parts.append(f"用途：{s.use_case}")
    if s.budget_min is not None or s.budget_max is not None:
        lo = int(round(s.budget_min or 0))
        hi = int(round(s.budget_max)) if s.budget_max is not None else "不限"
        parts.append(f"价格 {lo} 到 {hi} 元")
    for k, v in s.params.items():
        parts.append(f"{k}：{v}")
    if s.brand:
        parts.append(f"品牌：{s.brand}")
    if s.note:
        parts.append(s.note)
    return "；".join(parts)


def _prescore(p: dict, s: SlotState) -> float:
    score = 0.0
    price = float(p["price"])
    if s.budget_min is not None and s.budget_max is not None:
        center = (s.budget_min + s.budget_max) / 2
        span = max(s.budget_max - s.budget_min, 1)
        score += 40 * (1 - min(abs(price - center) / span, 1))
    elif s.budget_max is not None:
        score += 40 * (price / s.budget_max) if price <= s.budget_max else 0
    attrs = p.get("attributes", {})
    for k in (s.params or {}):
        if attrs.get(k):
            score += 15
    if s.category and p.get("category") == s.category:
        score += 20
    if s.brand and s.brand in p.get("brand", ""):
        score += 15
    return score


def search_nl(query: str, category: str | None = None, top_n: int = 20) -> list[dict]:
    """自然语言搜索，返回完整商品记录（含商家维护的营销位字段）。"""
    # 1. LLM 抽槽位
    slots = SlotState()
    try:
        delta = llm.extract_intent(query, {}, [])
        slots.merge(delta)
    except Exception:
        pass
    if category and not slots.category:
        slots.category = category

    # 2. 结构化过滤(text2sql 真SQL, 失败降级内存)
    filtered = []
    if settings.ENABLE_TEXT2SQL:
        try:
            filtered = text2sql.search(_slot_text(slots))
        except Exception:
            filtered = []
    if not filtered:
        filtered = catalog.sql_filter(slots)

    # 3. 向量语义召回
    semantic = []
    try:
        semantic = vector_store.search(query, top_k=30)
    except Exception:
        semantic = []

    # 4. 合并去重 + 粗排
    seen, merged = set(), []
    for p in filtered + semantic:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        merged.append(p)
    merged.sort(key=lambda p: -_prescore(p, slots))

    # text2sql / 向量库返回的记录字段不全，统一回查目录取完整记录（含营销位）
    out = []
    for p in merged[:top_n]:
        full = catalog.find_by_id(p["id"])
        out.append(full if full else p)
    return out
