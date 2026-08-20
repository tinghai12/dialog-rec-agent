"""商家端「订单助手」：用对话查看新订单、按距离与库存推荐最优仓、一键自动处理。

意图判定先走关键词规则（不依赖 LLM，断网也能用），规则拿不准时再交给 LLM 兜底。
每张订单卡片都会带上仓库选项与推荐理由，前端据此渲染交互按钮，最终由商家点确认。
"""
import re

from app.services import llm, order as order_svc

INTENTS = ("list_pending", "auto_process", "accept", "reject", "list_all", "aftersale", "help")

_RULES = [
    ("aftersale", ["售后", "退货", "退款", "换货", "维修", "投诉"]),
    ("auto_process", ["自动处理", "自动接单", "一键处理", "一键接单", "全部接单", "帮我处理", "都接了", "自动帮我"]),
    ("list_pending", ["新订单", "待接单", "待处理", "有单吗", "有新单", "看看订单", "查看订单", "订单情况"]),
    ("list_all", ["全部订单", "所有订单", "订单列表", "配送中", "历史订单"]),
    ("reject", ["拒单", "拒绝", "不接"]),
    ("accept", ["接单", "确认", "发货", "接了"]),
]


def _rule_intent(message: str) -> str | None:
    text = message.strip()
    for intent, keys in _RULES:
        if any(k in text for k in keys):
            return intent
    return None


def _llm_intent(message: str) -> str:
    system = (
        "你是电商商家后台的订单助手意图分类器。只输出 JSON。"
        f"intent 必须是其中之一：{list(INTENTS)}。"
        "list_pending=查看待接单的新订单；auto_process=让你自动处理/批量接单；"
        "accept=接受某个订单；reject=拒绝某个订单；list_all=查看全部订单；help=其它。"
        '输出格式：{"intent": "...", "order_no": "订单号或空"}'
    )
    try:
        data = llm._json(system, message)
        intent = data.get("intent")
        return intent if intent in INTENTS else "help"
    except Exception:
        return "help"


def _order_no_in(message: str) -> str | None:
    m = re.search(r"\bD\d{14}[A-Z0-9]{6}\b", message.upper())
    return m.group(0) if m else None


def _decorate(merchant_id: int, orders: list[dict], with_options: bool = True) -> list[dict]:
    """给待接单的订单挂上仓库选项与推荐仓，供前端画交互按钮。"""
    out = []
    for o in orders:
        card = dict(o)
        if with_options and o["status"] == "pending":
            try:
                opt = order_svc.warehouse_options(merchant_id, o["order_no"])
                card["warehouses"] = opt["warehouses"]
                card["recommended_id"] = opt["recommended_id"]
                best = next((w for w in opt["warehouses"] if w["id"] == opt["recommended_id"]), None)
                card["recommendation"] = (
                    f"建议由「{best['name']}」发货：{best['reason']}" if best else "该店铺还没有配置仓库"
                )
            except order_svc.OrderError:
                card["warehouses"] = []
        out.append(card)
    return out


def _summary(orders: list[dict]) -> str:
    total = sum(o["total_amount"] for o in orders)
    return f"{len(orders)} 笔、合计 ¥{total:,.0f}"


def handle(merchant_id: int, message: str) -> dict:
    """返回 {reply, order_cards, action}。"""
    intent = _rule_intent(message) or _llm_intent(message)
    order_no = _order_no_in(message)

    if intent == "list_pending":
        pending = order_svc.merchant_orders(merchant_id, "pending")
        if not pending:
            return {"reply": "目前没有待接单的新订单，我会盯着，有新单随时问我。",
                    "order_cards": [], "action": "none"}
        cards = _decorate(merchant_id, pending)
        lack = [c for c in cards if c.get("recommended_id") is None and c.get("warehouses")]
        tip = f"其中 {len(lack)} 笔所有仓都缺货，需要你手动处理。" if lack else "我已按「库存满足 + 距离最近」标出推荐仓。"
        return {
            "reply": f"有 {_summary(pending)} 待接单。{tip}你可以逐单确认，也可以让我自动处理。",
            "order_cards": cards, "action": "list_pending",
        }

    if intent == "auto_process":
        pending = order_svc.merchant_orders(merchant_id, "pending")
        if not pending:
            return {"reply": "现在没有待接单的订单，不用处理。", "order_cards": [], "action": "none"}
        done, skipped = [], []
        for o in pending:
            try:
                result = order_svc.accept_order(merchant_id, o["order_no"])
                done.append((o["order_no"], result["origin_name"], result["eta_minutes"]))
            except order_svc.OrderError as e:
                skipped.append((o["order_no"], str(e)))
        lines = [f"· {no} → 由「{wh}」发货，预计 {eta} 分钟送达" for no, wh, eta in done]
        reply = f"已自动接单 {len(done)} 笔：\n" + "\n".join(lines) if done else "没有能自动接单的订单。"
        if skipped:
            reply += "\n\n以下订单需要你手动处理：\n" + "\n".join(f"· {no}：{why}" for no, why in skipped)
        remain = order_svc.merchant_orders(merchant_id, "pending")
        return {"reply": reply, "order_cards": _decorate(merchant_id, remain), "action": "auto_processed"}

    if intent == "accept":
        if not order_no:
            pending = order_svc.merchant_orders(merchant_id, "pending")
            if not pending:
                return {"reply": "现在没有待接单的订单。", "order_cards": [], "action": "none"}
            return {"reply": "要接哪一单？下面是待接单列表，点卡片上的按钮确认，或者把订单号发我。",
                    "order_cards": _decorate(merchant_id, pending), "action": "list_pending"}
        try:
            result = order_svc.accept_order(merchant_id, order_no)
        except order_svc.OrderError as e:
            return {"reply": str(e), "order_cards": [], "action": "none"}
        return {
            "reply": f"{order_no} 已接单，由「{result['origin_name']}」发货，预计 {result['eta_minutes']} 分钟送达。",
            "order_cards": [result], "action": "accepted",
        }

    if intent == "reject":
        if not order_no:
            return {"reply": "拒单要指定订单号，把订单号发我，或者在订单卡片上点拒单。",
                    "order_cards": _decorate(merchant_id, order_svc.merchant_orders(merchant_id, "pending")),
                    "action": "list_pending"}
        try:
            result = order_svc.reject_order(merchant_id, order_no)
        except order_svc.OrderError as e:
            return {"reply": str(e), "order_cards": [], "action": "none"}
        return {"reply": f"{order_no} 已拒单。", "order_cards": [result], "action": "rejected"}

    if intent == "aftersale":
        pending = order_svc.aftersale_orders(merchant_id)
        if not pending:
            return {"reply": "目前没有等待处理的售后申请。", "order_cards": [], "action": "none"}
        lines = []
        for o in pending[:5]:
            lines.append(f"· {o['order_no']}（{o['aftersale_type_text']}）：{o['aftersale_reason'] or '买家未填原因'}")
        return {
            "reply": f"有 {len(pending)} 笔售后等你处理：\n" + "\n".join(lines) +
                     "\n\n在卡片上点「同意」或「拒绝」即可，也可以把订单号发我。",
            "order_cards": pending, "action": "aftersale",
        }

    if intent == "list_all":
        orders = order_svc.merchant_orders(merchant_id)
        if not orders:
            return {"reply": "还没有任何订单。", "order_cards": [], "action": "none"}
        shipping = [o for o in orders if o["status"] == "shipping"]
        return {
            "reply": f"共 {_summary(orders)}，其中 {len(shipping)} 笔在配送中。",
            "order_cards": _decorate(merchant_id, orders[:10]), "action": "list_all",
        }

    pending_n = order_svc.pending_count(merchant_id)
    aftersale_n = order_svc.aftersale_count(merchant_id)
    return {
        "reply": (f"我是订单助手，现在有 {pending_n} 笔新订单、{aftersale_n} 笔待处理售后。你可以让我：\n"
                  "· 「看看新订单」——列出待接单，并按库存和距离推荐发货仓\n"
                  "· 「自动处理订单」——我按推荐仓批量接单，缺货的留给你\n"
                  "· 「有售后吗」——列出等待处理的售后申请\n"
                  "· 「接单 D2026…」/「拒单 D2026…」——处理指定订单"),
        "order_cards": [], "action": "help",
    }
