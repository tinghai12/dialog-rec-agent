"""对话编排 —— 系统的心脏。

核心思路：用 LLM 理解用户意图（含上下文指代），而不是用正则硬编码。
流程：收消息 → LLM 意图分类 → 按意图路由（推荐/反事实/追问品牌/改偏好/闲聊）
LLM 失败时降级到正则 + 槽位抽取的旧逻辑，保证系统不崩。
"""
import copy
import re

from app.core.config import settings
from app.services import cart, catalog, favorites, llm, order as order_svc, text2sql, vector_store
from app.services.session_store import get_or_create, save as session_save

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}

# 一句话内推荐几款
TOP_K = 3
# 送进 LLM 重排的候选上限（粗排后截断，控制 token 成本）
RERANK_POOL = 15


def _prescore(p: dict, slots) -> float:
    """规则粗排打分（不花钱）。硬约束已由 SQL 保证，这里排"更贴合"的。"""
    score = 0.0
    price = float(p["price"])
    # 价格贴近预算中心（用户通常想买预算内偏上的）
    if slots.budget_min is not None and slots.budget_max is not None:
        center = (slots.budget_min + slots.budget_max) / 2
        span = max(slots.budget_max - slots.budget_min, 1)
        score += 40 * (1 - min(abs(price - center) / span, 1))
    elif slots.budget_max is not None:
        score += 40 * (price / slots.budget_max) if price <= slots.budget_max else 0
    # 参数满足度：要求的每项都满足则加分
    attrs = p.get("attributes", {})
    for k, v in (slots.params or {}).items():
        actual = attrs.get(k)
        if actual:
            score += 15
    # 品类一致
    if slots.category and p.get("category") == slots.category:
        score += 20
    # 品牌命中
    if slots.brand and slots.brand in p.get("brand", ""):
        score += 15
    return score


def _card(p: dict, reason: str = "", con: str = "") -> dict:
    return {
        "id": p["id"],
        "title": p["title"],
        "brand": p["brand"],
        "category": p["category"],
        "price": float(p["price"]),
        "attributes": p.get("attributes", {}),
        "pros": p.get("pros", []),
        "reason": reason,
        "con": con,
        # 卡片配图：商家上传的主图，没有则由前端按下列文案生成兜底海报
        "main_image": p.get("main_image") or "",
        "poster_bg": p.get("poster_bg") or "",
        "poster_headline": p.get("poster_headline") or "",
        "final_price": p.get("final_price"),
    }


def _current_slots_dict(s):
    return s.slots.to_dict()


def _missing_critical(slots) -> list[str]:
    """判断还缺哪些关键信息，决定是否追问（优先级：品类>用途>预算>配置）。
    品牌不主动追问（用户没指定时无需强求）。"""
    missing = []
    if not slots.category:
        missing.append("category")
    elif not slots.use_case:
        missing.append("use_case")
    elif slots.budget_min is None and slots.budget_max is None:
        missing.append("budget")
    elif not slots.params:
        missing.append("params")
    return missing


def _ask_one_question(missing: list[str]) -> str:
    if "category" in missing:
        return "想买什么？笔记本还是手机？我好按这个方向帮你挑。"
    if "use_case" in missing:
        return "想先了解下你的使用场景：主要是日常办公、写代码/编程，还是玩游戏或看视频？"
    if "budget" in missing:
        return "预算大概多少？我好帮你在这个范围内挑。"
    if "params" in missing:
        return "有没有特别要求的配置？比如内存大小、机身重量或续航时长。"
    return "还有什么想补充的吗？"


def _build_query(slots, message: str) -> str:
    """用槽位信息构造语义检索 query，替代纯 message+note。"""
    parts = [message.strip() or slots.use_case or ""]
    if slots.budget_min or slots.budget_max:
        parts.append(f"预算{slots.budget_min or ''}到{slots.budget_max or ''}元")
    for k, v in slots.params.items():
        parts.append(f"{k}{v}")
    if slots.brand:
        parts.append(slots.brand)
    if slots.note:
        parts.append(slots.note)
    return " ".join(p for p in parts if p)


def _slots_to_text(slots) -> str:
    """把槽位转成自然语言需求文本，供 text2sql 生成 SQL。"""
    parts = []
    if slots.category:
        parts.append(f"品类：{slots.category}")
    if slots.use_case:
        parts.append(f"用途：{slots.use_case}")
    if slots.budget_min is not None and slots.budget_max is not None:
        parts.append(f"价格 {slots.budget_min:.0f} 到 {slots.budget_max:.0f} 元")
    elif slots.budget_max is not None:
        parts.append(f"价格不超过 {slots.budget_max:.0f} 元")
    elif slots.budget_min is not None:
        parts.append(f"价格不低于 {slots.budget_min:.0f} 元")
    for k, v in slots.params.items():
        parts.append(f"{k}：{v}")
    if slots.brand:
        parts.append(f"品牌：{slots.brand}")
    if slots.exclude:
        parts.append("排除品牌：" + "、".join(slots.exclude))
    if slots.note:
        parts.append(slots.note)
    return "；".join(p for p in parts if p)


def _merge_retrieval(slots, query: str, exclude_ids: list[int]) -> list[dict]:
    """召回：结构化过滤(text2sql 真SQL,失败降级内存) + 语义检索合并，去重、剔除已排除。"""
    filtered = []
    if settings.ENABLE_TEXT2SQL:
        try:
            filtered = text2sql.search(_slots_to_text(slots))
        except Exception:
            filtered = []
    if not filtered:
        filtered = catalog.sql_filter(slots)
    semantic = vector_store.search(query, top_k=50)

    seen = set()
    merged = []
    for p in filtered + semantic:
        if p["id"] in seen or p["id"] in exclude_ids:
            continue
        seen.add(p["id"])
        merged.append(p)
    return merged


def _relax_retrieval(slots, query: str, exclude_ids: list[int]) -> list[dict]:
    """候选不足时，去掉过严的参数要求放宽召回。"""
    if not slots.params:
        return []
    relaxed = copy.copy(slots)
    relaxed.params = {}
    return _merge_retrieval(relaxed, query, exclude_ids)


def _explain_reject(slots, target: dict) -> str:
    """给出某商品没被推荐的原因（反事实解释用）。"""
    price = float(target["price"])
    reasons = []
    if slots.budget_min is not None and price < slots.budget_min:
        reasons.append(f"低于你的预算下限 {slots.budget_min:.0f} 元")
    if slots.budget_max is not None and price > slots.budget_max:
        reasons.append(f"超出你的预算 {slots.budget_max:.0f} 元")
    if slots.brand and slots.brand not in target["brand"]:
        reasons.append(f"不是你要的 {slots.brand}")
    if any(ex in target["brand"] or ex in target["title"] for ex in slots.exclude):
        reasons.append("在你明确排除的范围内")
    return "；".join(reasons) if reasons else "它在所有候选里排在 Top-3 之外"


def _norm_text(s: str) -> str:
    """归一化：小写、去掉空格和横杠，用于模糊匹配。"""
    return s.lower().replace(" ", "").replace("-", "").replace("_", "")


def _normalize_brand(name: str) -> str:
    """把纯别名归一化到标准品牌名（仅精确匹配，不做子串吞字）。"""
    alias_map = {
        "mac": "苹果", "macbook": "苹果", "macbookpro": "苹果", "macbookair": "苹果",
        "apple": "苹果", "iphone": "苹果",
        "华为": "华为", "huawei": "华为", "mate": "华为",
        "联想": "联想", "lenovo": "联想", "thinkpad": "联想", "thinkbook": "联想", "小新": "联想",
        "小米": "小米", "xiaomi": "小米", "mi": "小米", "红米": "小米", "redmi": "小米",
        "荣耀": "荣耀", "honor": "荣耀",
        "华硕": "华硕", "asus": "华硕", "rog": "华硕", "灵耀": "华硕",
        "惠普": "惠普", "hp": "惠普", "战66": "惠普", "战x": "惠普",
        "机械革命": "机械革命",
        "苹果笔记本": "苹果", "苹果电脑": "苹果", "苹果手机": "苹果",
    }
    n = _norm_text(name)
    if n in alias_map:
        return alias_map[n]
    return name


def _find_target_product(raw_target: str, slots=None) -> dict | None:
    """在目录中找目标商品，按匹配度打分，取最高分。

    若 slots 有 category(笔记本/手机)，优先匹配同品类——避免用户聊手机时
    反事实解释回答 MacBook Air 这种跨品类低级错误。
    """
    n_target = _norm_text(raw_target)
    n_brand = _norm_text(_normalize_brand(raw_target))
    category = (slots or {}).get("category") if slots else None
    best = None
    best_score = 0
    for p in catalog.get_all():
        title_n = _norm_text(p["title"])
        brand_n = _norm_text(p["brand"])
        score = 0
        if n_target and n_target in title_n:
            score = 200 + len(n_target)
        elif n_brand and n_brand == brand_n:
            score = 100
        elif n_brand and n_brand in title_n:
            score = 80
        elif n_target and n_target in brand_n:
            score = 60
        # 品类匹配奖励：同品类加分，跨品类降权
        if category and p.get("category") == category:
            score += 50
        elif category and p.get("category") != category:
            score -= 30
        if score > best_score:
            best_score = score
            best = p
    return best


def _brand_products(brand: str, slots) -> list[dict]:
    """找某品牌的所有商品，优先用当前槽位过滤，过滤为空则只看品牌。"""
    brand = _normalize_brand(brand)
    # 先在满足硬约束的商品里找该品牌
    filtered = [p for p in catalog.sql_filter(slots) if p["brand"] == brand]
    if filtered:
        return filtered
    # 过滤后为空，退化为只看品牌
    return [p for p in catalog.get_all() if p["brand"] == brand]


# ============ 各意图处理函数 ============

def _recommend(session, message: str) -> dict:
    """召回 + 重排 + 解释，返回推荐结果（不含 session_id）。"""
    # 信息不足 → 追问（最多追问 3 次覆盖 用途→预算→配置，避免死循环）
    missing = _missing_critical(session.slots)
    if missing and not session.slots.note and session.clarify_asked < 3:
        question = _ask_one_question(missing)
        session.clarify_asked += 1
        session.history.append({"role": "assistant", "content": question})
        return {
            "reply": question,
            "cards": [],
            "needs_more": True,
            "slots": _current_slots_dict(session),
        }

    exclude_ids = list(set(session.rejected_ids) | set(session.pending_exclude))
    query = _build_query(session.slots, message)
    candidates = _merge_retrieval(session.slots, query, exclude_ids)

    # 回退1：池子被"换一批"排空时，放弃临时排除
    if not candidates:
        candidates = _merge_retrieval(session.slots, query, list(set(session.rejected_ids)))
        if candidates:
            session.pending_exclude.clear()

    # 回退2：候选太少(<5)时，去掉过严参数放宽召回
    if len(candidates) < 5:
        relaxed = _relax_retrieval(session.slots, query, list(set(session.rejected_ids)))
        if relaxed:
            candidates = relaxed

    if not candidates:
        reply = "按当前条件没找到合适的商品。要不放宽点预算，或去掉某个配置要求试试？"
        session.history.append({"role": "assistant", "content": reply})
        return {
            "reply": reply,
            "cards": [],
            "needs_more": False,
            "slots": _current_slots_dict(session),
        }

    # 规则粗排 → 截断到 RERANK_POOL，控制 LLM 重排的 token 成本
    pool = sorted(candidates, key=lambda p: -_prescore(p, session.slots))[:RERANK_POOL]

    # 重排：传入已展示 id，优先选未展示的
    try:
        ranked = llm.rerank(session.slots.to_dict(), pool, session.shown_ids)
        if not ranked:
            raise llm.LLMError("重排返回空")
    except llm.LLMError:
        ranked = [{"id": p["id"], "reason": "", "con": ""} for p in pool[:TOP_K]]

    cards = []
    for r in ranked[:TOP_K]:
        p = catalog.find_by_id(int(r["id"]))
        if p:
            cards.append(_card(p, r.get("reason", ""), r.get("con", "")))

    # 程序化兜底：若候选充足但返回全是已展示的，用未展示候选替换
    if cards and len([c for c in cards if c["id"] in session.shown_ids]) == len(cards):
        fresh = [p for p in candidates if p["id"] not in session.shown_ids]
        if len(fresh) >= TOP_K:
            cards = [_card(p) for p in fresh[:TOP_K]]

    # 评审 Agent：校验推荐（可通过 ENABLE_REVIEW=0 关闭以省 token）
    review = {"pass": True, "issues": []}
    if settings.ENABLE_REVIEW:
        try:
            review = llm.review_recommendation(session.slots.to_dict(), cards, pool)
        except Exception:
            pass

    session.last_decision = {
        "turn": session.turn_no,
        "query_slots": _current_slots_dict(session),
        "candidates": [p["id"] for p in candidates],
        "ranked": [c["id"] for c in cards],
        "review": review,
    }
    session.shown_ids.extend([c["id"] for c in cards])

    reply = "根据你的需求，给你推荐这几款："
    if session.slots.params.get("重量"):
        reply = "好的，按新的重量要求重新筛选，这几款更合适："
    session.history.append({"role": "assistant", "content": reply})

    return {
        "reply": reply,
        "cards": cards,
        "needs_more": False,
        "slots": _current_slots_dict(session),
        "decision": session.last_decision,
    }


def _counterfactual(session, intent: dict) -> dict:
    """反事实解释：为什么没推 X。"""
    target_name = (intent.get("target_item") or intent.get("target_brand") or "").strip()
    target = _find_target_product(target_name, session.slots.to_dict()) if target_name else None
    if target is None:
        return {
            "reply": f"我看了下，目前商品库还没有{target_name or '这个'}相关的商品，暂时没法对比。",
            "cards": [],
            "needs_more": False,
        }
    reason = _explain_reject(session.slots, target)
    recommended = [catalog.find_by_id(i) for i in session.shown_ids[-3:] if catalog.find_by_id(i)]
    try:
        text = llm.explain_counterfactual(session.slots.to_dict(), target, reason, recommended)
    except Exception:
        text = f"这款没入选，主要是因为{reason}。"
    return {"reply": text, "cards": [], "needs_more": False}


def _item_list(session, intent: dict) -> dict:
    """追问某品牌有哪些可选。"""
    brand = (intent.get("target_brand") or intent.get("target_item") or "").strip()
    items = _brand_products(brand, session.slots)
    if not items:
        # 品牌名可能不准，用模糊匹配兜底
        t = _find_target_product(brand) if brand else None
        if t:
            brand = t["brand"]
            items = _brand_products(brand, session.slots)
    if not items:
        return {
            "reply": f"目前没有找到{brand or '这个品牌'}相关的商品。",
            "cards": [],
            "needs_more": False,
        }
    try:
        intro = llm.item_list_intro(brand, items)
    except Exception:
        intro = f"{brand}目前有这几款可选："
    try:
        ranked = llm.rerank(session.slots.to_dict(), items)
        if not ranked:
            raise llm.LLMError("空")
    except llm.LLMError:
        ranked = [{"id": p["id"], "reason": "", "con": ""} for p in items[:TOP_K]]
    cards = []
    for r in ranked[:TOP_K]:
        p = catalog.find_by_id(int(r["id"]))
        if p:
            cards.append(_card(p, r.get("reason", ""), r.get("con", "")))
    session.shown_ids.extend([c["id"] for c in cards])
    return {"reply": intro, "cards": cards, "needs_more": False}


def _detail(session, intent: dict, message: str) -> dict:
    """追问某款商品的具体信息。"""
    target_name = (intent.get("target_item") or intent.get("target_brand") or "").strip()
    target = _find_target_product(target_name, session.slots.to_dict()) if target_name else None
    if target is None and session.shown_ids:
        target = catalog.find_by_id(session.shown_ids[-1])
    if target is None:
        # 无上下文，用通用回复
        try:
            text = llm.generic_reply(message, session.history)
        except Exception:
            text = "可以告诉我你想了解哪款商品，我来帮你查参数。"
        return {"reply": text, "cards": [], "needs_more": False}
    try:
        text = llm.answer_detail(message, target)
    except Exception:
        text = f"{target['title']} 的价格是 ¥{float(target['price']):.0f}，配置详见商品卡片。"
    return {"reply": text, "cards": [], "needs_more": False}


def _confirm(session, message: str) -> dict:
    """确认/加购/结束。"""
    try:
        text = llm.generic_reply(message, session.history)
    except Exception:
        text = "好的，有需要随时找我。"
    return {"reply": text, "cards": [], "needs_more": False}


def _chat(session, message: str) -> dict:
    """闲聊。"""
    try:
        text = llm.generic_reply(message, session.history)
    except Exception:
        text = "我在呢，说说你的需求，我帮你挑。"
    return {"reply": text, "cards": [], "needs_more": False}


def _apply_refine(session, message: str, intent: dict) -> None:
    """处理偏好修改：换一批 / 拒绝具体商品 / 槽位增量。"""
    if any(w in message for w in ("换一批", "换几个", "换别的", "再换", "换一换")):
        session.pending_exclude.extend(session.shown_ids)
        session.shown_ids.clear()
    m = re.search(r"第\s*([一二三四五1-5])\s*个", message)
    if m and any(w in message for w in ("不要", "去掉", "换掉", "不行", "太重", "太贵", "不喜欢")):
        idx = _CN_NUM.get(m.group(1), int(m.group(1)))
        if 1 <= idx <= len(session.shown_ids):
            session.rejected_ids.append(session.shown_ids[idx - 1])
    session.slots.merge(intent.get("slots_delta", {}))


# ============ 旧正则逻辑（LLM 挂了的兜底） ============

def _fallback_regex(session, message: str) -> dict:
    """LLM 意图理解失败时的兜底：正则分支 + 槽位抽取。"""
    # 反事实
    m = re.search(r"为什么\s*(?:没|没有|不)(?:给我|给)?(?:推荐|推|选)\s*(.+?)[？?。]?$", message.strip())
    if m:
        raw = m.group(1).strip()
        if raw.startswith("我"):
            raw = raw[1:]
        target = _find_target_product(raw)
        if target:
            reason = _explain_reject(session.slots, target)
            try:
                text = llm.explain_counterfactual(session.slots.to_dict(), target, reason)
            except Exception:
                text = f"这款没入选，主要是因为{reason}。"
            return {"reply": text, "cards": [], "needs_more": False}

    # 换一批
    if "换一批" in message or "换几个" in message or "换别的" in message:
        session.pending_exclude.extend(session.shown_ids)
        session.shown_ids.clear()

    # 第N个不要
    m2 = re.search(r"第\s*([一二三四五1-5])\s*个", message)
    if m2 and any(w in message for w in ("不要", "去掉", "换掉", "不行")):
        idx = _CN_NUM.get(m2.group(1), int(m2.group(1)))
        if 1 <= idx <= len(session.shown_ids):
            session.rejected_ids.append(session.shown_ids[idx - 1])

    # 槽位抽取
    try:
        delta = llm.extract_intent(
            message,
            _current_slots_dict(session),
            [catalog.find_by_id(i) for i in session.shown_ids[-3:] if catalog.find_by_id(i)],
        )
        session.slots.merge(delta)
    except llm.LLMError:
        session.slots.note += message

    return _recommend(session, message)


# ============ 主入口 ============

def handle_message(session_id: str | None, message: str, user_id: int | None = None) -> dict:
    session = get_or_create(session_id, user_id)
    session.history.append({"role": "user", "content": message})
    session.turn_no += 1

    # 订单/售后类问题先走规则：这些意图不在推荐域的 LLM 意图表里
    order_intent = _order_intent(message)
    if order_intent:
        result = _handle_order_question(session, order_intent, message)
        result["session_id"] = session.session_id
        _attach_cards_to_history(session, result)
        session_save(session)
        return result

    # 优先用 LLM 理解意图
    intent = None
    try:
        context_products = [catalog.find_by_id(i) for i in session.shown_ids[-3:] if catalog.find_by_id(i)]
        intent = llm.classify_intent(message, session.history, _current_slots_dict(session), context_products)
    except Exception:
        intent = None

    it = (intent or {}).get("intent", "")

    if it == "counterfactual":
        result = _maybe_follow_up_clarify(session, _counterfactual(session, intent))
    elif it == "ask_item_list":
        result = _maybe_follow_up_clarify(session, _item_list(session, intent))
    elif it == "ask_detail":
        result = _maybe_follow_up_clarify(session, _detail(session, intent, message))
    elif it in ("add_to_fav", "add_to_cart", "remove_from_cart", "checkout", "my_orders", "my_favs"):
        result = _handle_ecommerce(session, intent)
    elif it == "refine_preference":
        _apply_refine(session, message, intent)
        result = _recommend(session, message)
    elif it in ("new_requirement", "clarify_answer"):
        session.slots.merge((intent or {}).get("slots_delta", {}))
        result = _recommend(session, message)
    elif it == "confirm":
        result = _maybe_follow_up_clarify(session, _confirm(session, message))
    elif it == "chat":
        result = _maybe_follow_up_clarify(session, _chat(session, message))
    else:
        # 意图不明确或 LLM 挂了，走正则兜底
        result = _fallback_regex(session, message)

    result["session_id"] = session.session_id
    _attach_cards_to_history(session, result)
    session_save(session)
    return result


def _attach_cards_to_history(session, result: dict) -> None:
    """把本轮推荐卡片挂到历史的最后一条助手消息上，供刷新/切回会话时还原。

    部分分支只返回 reply 未写 history，这里一并补齐，避免历史缺回复。
    """
    cards = result.get("cards") or []
    reply = result.get("reply", "")
    last = session.history[-1] if session.history else None
    if not last or last.get("role") != "assistant":
        session.history.append({"role": "assistant", "content": reply, "cards": cards})
        return
    if cards:
        last["cards"] = cards


# ============ 订单 / 售后（买家侧订单助手） ============

_ORDER_RULES = [
    ("aftersale", ["申请售后", "售后", "退货", "退款", "换货", "报修", "维修"]),
    ("track", ["到哪了", "到哪儿了", "快递", "物流", "配送到", "送到哪", "什么时候到", "还要多久", "运输状态", "配送状态"]),
    ("my_orders", ["我的订单", "订单状态", "查订单", "查看订单", "订单情况", "买了什么"]),
]

_AFTERSALE_KINDS = [
    ("return", ["退货"]),
    ("exchange", ["换货", "换一个", "换新"]),
    ("repair", ["维修", "报修", "修一下"]),
    ("refund", ["退款", "退钱", "仅退款"]),
]


def _order_intent(message: str) -> str | None:
    for intent, keys in _ORDER_RULES:
        if any(k in message for k in keys):
            return intent
    return None


def _aftersale_kind(message: str) -> str:
    for kind, keys in _AFTERSALE_KINDS:
        if any(k in message for k in keys):
            return kind
    return "refund"


def _pick_order(orders: list[dict], message: str) -> dict | None:
    """从消息里定位订单：优先订单号，其次「第N个」，再次最近一笔。"""
    m = re.search(r"\bD\d{14}[A-Z0-9]{6}\b", message.upper())
    if m:
        return next((o for o in orders if o["order_no"] == m.group(0)), None)
    m2 = re.search(r"第\s*([一二三四五1-5])\s*[个笔单]", message)
    if m2:
        idx = _CN_NUM.get(m2.group(1), int(m2.group(1)) if m2.group(1).isdigit() else 1)
        if 1 <= idx <= len(orders):
            return orders[idx - 1]
    return orders[0] if orders else None


def _handle_order_question(session, intent: str, message: str) -> dict:
    if not session.user_id:
        return {"reply": "查订单要先登录，去右上角登录一下就能看了。",
                "cards": [], "needs_more": False, "action": "need_login"}

    orders = order_svc.list_orders(session.user_id)
    if not orders:
        return {"reply": "你还没有订单，去逛逛下单吧。", "cards": [], "needs_more": False}

    if intent == "aftersale":
        target = _pick_order(orders, message)
        kind = _aftersale_kind(message)
        # 明确指向某一单才直接提交，否则先让用户确认是哪一单
        explicit = bool(re.search(r"\bD\d{14}[A-Z0-9]{6}\b", message.upper())
                        or re.search(r"第\s*[一二三四五1-5]\s*[个笔单]", message))
        if not explicit and len(orders) > 1:
            return {
                "reply": f"你有 {len(orders)} 笔订单，要给哪一笔申请售后？在卡片上点「申请售后」，或者告诉我第几笔。",
                "cards": [], "order_cards": orders[:8], "needs_more": False, "action": "pick_aftersale",
            }
        try:
            updated = order_svc.apply_aftersale(session.user_id, target["order_no"], kind, message[:120])
        except order_svc.OrderError as e:
            return {"reply": str(e), "cards": [], "order_cards": [target], "needs_more": False}
        return {
            "reply": (f"已为订单 {updated['order_no']} 提交{updated['aftersale_type_text']}申请，"
                      f"已通知「{updated['shop_name']}」，商家处理后我会在这里告诉你。"),
            "cards": [], "order_cards": [updated], "needs_more": False, "action": "aftersale_applied",
        }

    if intent == "track":
        shipping = [o for o in orders if o["status"] == "shipping"]
        target = _pick_order(shipping or orders, message)
        if target["status"] == "shipping":
            text = (f"{target['rider_name']}正在从「{target['origin_name'] or '发货仓'}」送往 "
                    f"{target['address_text']}，已走了 {round(target['progress'] * 100)}%，"
                    f"预计还有 {target['remain_minutes']} 分钟送达。点卡片看实时轨迹。")
        elif target["status"] == "pending":
            text = f"订单 {target['order_no']} 还在等「{target['shop_name']}」接单，接单后就能看配送轨迹了。"
        elif target["status"] == "delivered":
            text = f"订单 {target['order_no']} 已经送达了。如果有问题可以跟我说申请售后。"
        else:
            text = f"订单 {target['order_no']} 状态：{target['status_text']}。"
        return {"reply": text, "cards": [], "order_cards": [target], "needs_more": False}

    # my_orders
    shipping = [o for o in orders if o["status"] == "shipping"]
    aftersale = [o for o in orders if o["aftersale_status"] == "pending"]
    parts = [f"你有 {len(orders)} 笔订单"]
    if shipping:
        parts.append(f"{len(shipping)} 笔配送中")
    if aftersale:
        parts.append(f"{len(aftersale)} 笔售后处理中")
    return {"reply": "，".join(parts) + "。点卡片可以看轨迹或申请售后。",
            "cards": [], "order_cards": orders[:8], "needs_more": False}


def _maybe_follow_up_clarify(session, result: dict) -> dict:
    """复合意图：反事实/闲聊/确认类回复后，若仍有缺失关键槽位，追加一句追问。

    例如用户说"为什么不推联想 还有你还没问我用途" → 反事实解释 + "另外，想先了解下你的使用场景..."
    """
    missing = _missing_critical(session.slots)
    if missing and session.clarify_asked < 3 and not result.get("needs_more"):
        q = _ask_one_question(missing)
        session.clarify_asked += 1
        result["reply"] = (result.get("reply") or "") + f" 另外，{q}"
        result["needs_more"] = True
    return result


# ============ 电商操作（自然语言购物核心） ============

def _resolve_ecommerce_product(session, intent: dict) -> dict | None:
    """解析"第几个/这个/某款"指代 → 商品。"""
    idx = intent.get("target_index")
    if idx is not None:
        try:
            i = int(idx)
            if 1 <= i <= len(session.shown_ids):
                return catalog.find_by_id(session.shown_ids[i - 1])
        except (TypeError, ValueError):
            pass
    name = (intent.get("target_item") or "").strip()
    if name:
        p = _find_target_product(name, session.slots.to_dict())
        if p:
            return p
    # 默认最近推荐的第一个
    if session.shown_ids:
        return catalog.find_by_id(session.shown_ids[-1])
    return None


def _handle_ecommerce(session, intent: dict) -> dict:
    """对话里的电商操作：收藏/加购/下单/查订单/查收藏。"""
    if not session.user_id:
        return {
            "reply": "要先登录才能做购物操作哦，去右上角登录一下。",
            "cards": [], "needs_more": False, "action": "need_login",
        }
    it = intent.get("intent", "")
    try:
        if it == "add_to_fav":
            p = _resolve_ecommerce_product(session, intent)
            if not p:
                return {"reply": "先让我推荐几款，再告诉我收藏哪个吧。", "cards": [], "needs_more": False}
            favorites.add(session.user_id, p["id"])
            return {"reply": f"已收藏：{p['title'][:24]}", "cards": [], "needs_more": False, "action": "favorited"}
        if it == "add_to_cart":
            p = _resolve_ecommerce_product(session, intent)
            if not p:
                return {"reply": "先让我推荐几款，再告诉我加哪个进购物车吧。", "cards": [], "needs_more": False}
            cart.add_to_cart(session.user_id, p["id"])
            return {"reply": f"已加入购物车：{p['title'][:24]}", "cards": [], "needs_more": False, "action": "added_cart"}
        if it == "remove_from_cart":
            p = _resolve_ecommerce_product(session, intent)
            items = cart.get_cart(session.user_id)
            target = next((c for c in items if c["product_id"] == (p["id"] if p else -1)), None)
            if target:
                cart.remove_cart_item(session.user_id, target["item_id"])
                return {"reply": "已从购物车移除。", "cards": [], "needs_more": False, "action": "cart_changed"}
            return {"reply": "购物车里没找到这个商品。", "cards": [], "needs_more": False}
        if it == "checkout":
            orders = order_svc.create_order(session.user_id)
            total = sum(o["total_amount"] for o in orders)
            if len(orders) == 1:
                text = (f"下单成功！订单号 {orders[0]['order_no']}，共 ¥{total:.0f}，"
                        f"已通知「{orders[0]['shop_name']}」，等商家接单后就能看配送轨迹。")
            else:
                text = (f"下单成功！商品来自 {len(orders)} 个店铺，已拆成 {len(orders)} 笔订单，"
                        f"合计 ¥{total:.0f}，等商家接单后就能看配送轨迹。")
            return {"reply": text, "cards": [], "order_cards": orders, "needs_more": False, "action": "ordered"}
        if it == "my_orders":
            orders = order_svc.list_orders(session.user_id)
            if not orders:
                return {"reply": "你还没有订单，去逛一逛下单吧。", "cards": [], "needs_more": False}
            shipping = [o for o in orders if o["status"] == "shipping"]
            if shipping:
                o = shipping[0]
                text = (f"你有 {len(orders)} 笔订单，其中 {len(shipping)} 笔正在配送。"
                        f"{o['rider_name']}正在送「{o['products'][0]['title'][:16]}」，"
                        f"预计还有 {o['remain_minutes']} 分钟送达，点卡片可以看实时轨迹。")
            else:
                text = f"你有 {len(orders)} 笔订单，最近一笔状态是「{orders[0]['status_text']}」。"
            return {"reply": text, "cards": [], "order_cards": orders[:8], "needs_more": False}
        if it == "my_favs":
            favs = favorites.list_favorites(session.user_id)
            if not favs:
                return {"reply": "你还没有收藏，遇到喜欢的就喊我收藏吧。", "cards": [], "needs_more": False}
            lines = [f"{f['title'][:24]} ¥{f['price']:.0f}" for f in favs[:8]]
            return {"reply": "你的收藏：\n" + "\n".join(lines), "cards": [], "needs_more": False}
    except cart.CartError as e:
        return {"reply": str(e), "cards": [], "needs_more": False}
    except order_svc.OrderError as e:
        return {"reply": str(e), "cards": [], "needs_more": False}
    return {"reply": "好的，收到。", "cards": [], "needs_more": False}
