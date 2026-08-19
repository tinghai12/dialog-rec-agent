"""大模型客户端（DeepSeek，OpenAI 兼容）。

所有"聪明"都来自这里：抽槽位 / 生成追问 / 重排 / 反事实解释。
统一走 HTTP，失败抛异常，由 orchestrator 捕获并降级。
"""
import json

import requests

from app.core.config import settings


class LLMError(Exception):
    pass


def _post(system: str, user: str, temperature: float = 0.3, max_tokens: int = 1500) -> str:
    if not settings.LLM_API_KEY:
        raise LLMError("未配置 LLM_API_KEY（见 .env）")
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except requests.RequestException as e:
        raise LLMError(f"LLM 调用失败: {e}") from e


def _json(system: str, user: str, temperature: float = 0.2) -> dict:
    """要求模型输出 JSON，并尽力解析（去掉代码围栏/多余文字）。"""
    content = _post(system, user, temperature=temperature, max_tokens=2000)
    text = content.strip()
    # 去掉 ```json ... ``` 围栏
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 兜底：截取第一个 { 到最后一个 } 再试
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except json.JSONDecodeError as ex:
                raise LLMError(f"LLM 未返回合法 JSON: {text[:200]}") from ex
        raise LLMError(f"LLM 未返回合法 JSON: {text[:200]}")


INTENT_SYSTEM = """你是推荐系统的需求理解模块。任务：从用户话术中抽取"购买偏好槽位"，输出 JSON。

可用的槽位键（只输出有变化/新增的字段，没提到就省略）：
- category: 品类（笔记本 或 手机）
- budget_min: 数字（元），预算下限
- budget_max: 数字（元），预算上限
- brand: 期望品牌
- use_case: 使用场景（如 写代码/办公/游戏/摄影/送礼）
- params: 配置要求，键用固定名称：内存/硬盘/重量/屏幕/续航/电池/显卡/摄像头/芯片/CPU，值带单位（如 {"内存":"32G","重量":"1.4kg"}）
- exclude: 明确不要的品牌或款式，数组
- note: 其他无法结构化的自然语言要求（存原文）

规则：
1. 只能输出一个 JSON 对象，不要任何解释文字。
2. 多轮对话要结合"当前槽位"判断增量，而不是重复已有信息。
3. 用户负面评价某推荐（如"第二个太重了"）→ 参考"当前推荐商品"的配置，输出收紧的 params。
4. 没有新信息时输出 {}。
5. 绝不要从否定句提取偏好："不玩游戏"→ use_case 不能填"游戏"；"不要苹果"→ brand 不能填"苹果"，要填进 exclude。
6. 用户提到"笔记本/电脑/手机"等品类词时，填进 category，不要填进 use_case。
"""


def extract_intent(message: str, current_slots: dict, context_products: list) -> dict:
    """抽槽位。返回增量字段。"""
    cur = json.dumps(current_slots, ensure_ascii=False)
    ctx = json.dumps(context_products[:5], ensure_ascii=False)
    user = (
        f"用户最新的话：{message}\n"
        f"当前槽位：{cur}\n"
        f"当前推荐过的商品(用于理解指代)：{ctx}"
    )
    return _json(INTENT_SYSTEM, user)


RERANK_SYSTEM = """你是购物推荐助手。根据用户的需求和候选商品列表，选出最匹配的 3 款并排序。

输出 JSON：
{"ranked":[{"id": 数字, "reason": "为什么推荐它(引用用户说过的具体需求，别写套话)", "con": "一条客观缺点"}]}

规则：
1. 只返回 3 款，id 必须是候选列表里存在的。
2. reason 必须对应用户的具体需求（预算/场景/参数），如"32G 内存能同时开多个 Docker 容器，符合你说的预算 7000"。
3. con 必须是商品的真实缺点，数据驱动，不要编造。没有明显缺点就写一条相对短板（如"机身偏重""无独立显卡"）。
4. 如果提供了"已展示过的商品 id"，优先选择未展示过的（避免反复推荐同样的），除非未展示的都不合适。
5. 只输出 JSON，不要解释文字。
"""


INTENT_CLASSIFY_SYSTEM = """你是对话推荐系统的"对话理解模块"。判断用户当前这句话的意图，输出 JSON。

意图类型(intent)只能是以下之一：
- new_requirement: 用户提出新需求或补充需求信息（品类/预算/场景/参数/品牌），如"写代码""7000左右""想要32G内存"
- refine_preference: 用户修改或否定已有偏好，如"太贵了""太重了""不要这个""换一批""不要小米的"
- counterfactual: 用户追问为什么没推荐某商品，如"为什么没推mac""为什么不推荐苹果"
- ask_item_list: 用户追问某品牌/型号有哪些可选，如"哪款""mac有哪些""苹果有哪几款""有联想的吗"
- ask_detail: 用户追问某商品的具体信息，如"这款续航多久""内存多大""多重"
- confirm: 用户确认、加购、下单、结束
- chat: 闲聊、打招呼、感谢等其他
- add_to_fav: 用户要收藏某商品，如"收藏第一款""收藏这个""加进收藏夹"
- add_to_cart: 用户要加入购物车，如"加入购物车""要这款""买这个""把第二款加购"
- remove_from_cart: 用户要从购物车删除，如"从购物车删掉这个"
- checkout: 用户要下单/结算，如"下单""结算""提交订单""就买这些"
- my_orders: 用户要看订单，如"我的订单""查一下订单""买了什么"
- my_favs: 用户要看收藏，如"我的收藏""收藏夹"

关键规则（务必遵守）：
1. 必须结合"对话历史"理解指代！例如上一轮助手说"这款 MacBook Air 性价比不如其他"，用户接着问"哪款"，意图是 ask_item_list 且 target_brand 是苹果，而不是重新推荐。
2. target_brand 填归一化后的品牌名（苹果/华为/联想/小米/荣耀/华硕/惠普/机械革命/真我/红米/OPPO/iQOO 等），没有就填 null。
3. target_item 填具体商品名或型号（如 MacBook Air、ThinkPad、MateBook），没有就填 null。
4. target_index 填用户指的"第几个"（如"第一款""第二个"→1/2），没有明确指代就填 null。
5. slots_delta 只在有新的槽位信息时填，键用 category/budget_min/budget_max/brand/use_case/params/exclude，没新信息就填 {}。
6. category 填用户明确说的品类（"笔记本"或"手机"）；用户没提品类就省略 category 字段。
7. 理解指代时结合"当前推荐的商品"：比如"第二个太重了"，要参考第二个商品的重量，在 params 里给出收紧后的重量要求（如 {"重量":"1.4kg"}）。
8. 绝不要从否定句提取偏好！用户说"不玩游戏""不要苹果"，use_case 不能填"游戏"、brand 不能填"苹果"。
9. 只输出一个 JSON 对象，不要任何解释文字。
"""


def classify_intent(message: str, history: list, current_slots: dict, context_products: list | None = None) -> dict:
    """理解用户意图（含上下文指代）。返回 {intent, target_brand, target_item, slots_delta}。"""
    # 精简历史：最近 4 条，避免过长（省 token）
    recent = history[-4:] if history else []
    hist_json = json.dumps(recent, ensure_ascii=False)
    slots_json = json.dumps(current_slots, ensure_ascii=False)
    ctx_json = json.dumps(
        [
            {"title": p["title"], "price": float(p["price"]), "attributes": p.get("attributes", {})}
            for p in (context_products or [])[:3]
        ],
        ensure_ascii=False,
    ) if context_products else "[]"
    user = (
        f"当前槽位：{slots_json}\n"
        f"对话历史：{hist_json}\n"
        f"当前推荐的商品(用于理解指代)：{ctx_json}\n"
        f"用户最新消息：{message}\n"
        f"请判断这句话的意图。"
    )
    return _json(INTENT_CLASSIFY_SYSTEM, user)


GENERIC_REPLY_SYSTEM = """你是购物推荐助手。根据对话历史，用自然、口语化的方式回复用户。
像真人导购一样，简短自然。只输出回复文字，不要 JSON、不要列点、不要推荐商品（除非用户明确要推荐）。
"""


def generic_reply(message: str, history: list) -> str:
    """闲聊/确认类消息的通用自然回复。"""
    recent = history[-6:] if history else []
    hist_json = json.dumps(recent, ensure_ascii=False)
    user = f"对话历史：{hist_json}\n用户最新消息：{message}"
    return _post(GENERIC_REPLY_SYSTEM, user, temperature=0.7, max_tokens=400)


ITEM_LIST_SYSTEM = """你是购物推荐助手。用户在追问某品牌/型号有哪些可选，你要自然地把这些商品介绍出来。
根据给定商品列表，生成一句自然的引导语（如"苹果目前符合你需求的有这几款："），不要逐条复述参数，简短即可。
只输出引导语文字，不要 JSON、不要列点。
"""


def item_list_intro(brand: str, items: list) -> str:
    """生成"某品牌有哪些可选"的自然引导语。"""
    items_json = json.dumps(
        [{"title": p["title"], "price": float(p["price"]), "attrs": p.get("attributes", {})}
         for p in items[:8]],
        ensure_ascii=False,
    )
    user = f"品牌：{brand}\n可选商品：{items_json}"
    return _post(ITEM_LIST_SYSTEM, user, temperature=0.6, max_tokens=300)


DETAIL_SYSTEM = """你是购物推荐助手。用户在追问某款商品的具体信息（续航/内存/重量/价格等），
请结合给定的商品信息准确回答，不要编造商品信息里没有的内容。语气自然，像真人导购。
只输出回答文字，不要 JSON、不要列点。
"""


def answer_detail(question: str, product: dict) -> str:
    """回答关于某款商品的具体问题。"""
    prod = json.dumps(
        {
            "title": product.get("title"),
            "brand": product.get("brand"),
            "price": float(product.get("price", 0)),
            "attributes": product.get("attributes", {}),
            "cons": product.get("cons", []),
        },
        ensure_ascii=False,
    )
    user = f"商品信息：{prod}\n用户问题：{question}"
    return _post(DETAIL_SYSTEM, user, temperature=0.3, max_tokens=300)


def rerank(slots: dict, candidates: list, shown_ids: list | None = None) -> list:
    """对候选做 LLM 重排。返回 [{"id":..., "reason":..., "con":...}, ...]。

    候选字段精简（省 token）：id/标题/价格/品牌/关键属性，不传 cons（缺点由模型据属性自行判断）。
    """
    slots_json = json.dumps(slots, ensure_ascii=False)
    _KEY_ATTRS = ("内存", "硬盘", "重量", "屏幕", "CPU", "显卡", "电池", "摄像头", "芯片")
    cand_json = json.dumps(
        [
            {
                "id": p["id"],
                "t": p["title"][:30],
                "p": float(p["price"]),
                "b": p["brand"],
                "a": {k: v for k, v in (p.get("attributes") or {}).items() if k in _KEY_ATTRS},
            }
            for p in candidates
        ],
        ensure_ascii=False,
    )
    shown_part = f"\n已展示过的商品 id(优先避开)：{json.dumps(shown_ids or [], ensure_ascii=False)}" if shown_ids else ""
    user = f"用户需求：{slots_json}\n候选商品(t=标题 p=价格 b=品牌 a=属性)：{cand_json}{shown_part}"
    data = _json(RERANK_SYSTEM, user)
    ranked = data.get("ranked", [])
    return [r for r in ranked if isinstance(r, dict) and "id" in r][:3]


COUNTERFACTUAL_SYSTEM = """你是购物推荐助手的解释模块。用户问"为什么没推荐某商品"，你要给出真实、有说服力的反事实解释。

关键要求：不要泛泛而谈（如"性价比不如"），要引用具体数字和参数做对比：
- 预算对比：目标商品价格 vs 用户预算 / 当前推荐商品价格（如"ThinkPad T 同配 8299，超你预算 1300"）
- 参数对比：目标商品和当前推荐商品在 内存/重量/屏幕/CPU/显卡 等关键属性上的实际差异（如"它 16G 内存开 4 个 Docker 容器会吃紧"）
- 排除原因：如果因品牌/排除项被排除，明确指出

依据给定信息，用 1-3 句话解释。语气自然，像真人导购。
只输出解释文字，不要 JSON、不要列点。
"""


def explain_counterfactual(slots: dict, target_product: dict, reason: str, recommended_products: list | None = None) -> str:
    slots_json = json.dumps(slots, ensure_ascii=False)
    prod_json = json.dumps(
        {k: target_product.get(k) for k in ("title", "brand", "price", "attributes")},
        ensure_ascii=False,
    )
    rec_part = ""
    if recommended_products:
        rec_part = "\n当前推荐给用户的商品(用于对比)：\n" + json.dumps(
            [
                {"title": p.get("title"), "price": float(p.get("price", 0)),
                 "brand": p.get("brand"), "attributes": p.get("attributes", {})}
                for p in recommended_products[:3]
            ],
            ensure_ascii=False,
        )
    user = f"用户需求：{slots_json}\n用户想知道的商品：{prod_json}{rec_part}\n没推荐它的原因：{reason}"
    return _post(COUNTERFACTUAL_SYSTEM, user, temperature=0.6, max_tokens=400)


REVIEW_SYSTEM = """你是推荐系统的"评审 Agent"，专门负责挑刺、检查推荐是否合格。

给定用户需求、候选商品列表和最终推荐结果，检查以下方面，输出 JSON：
{"pass": true/false, "issues": [{"level": "hard"/"soft", "product_id": 数字或null, "msg": "问题描述"}]}

检查项：
1. 硬约束(level=hard)：推荐的商品是否满足用户硬性要求？
   - 预算：price 是否在 budget_min~budget_max 区间内
   - 品牌：是否出现了用户明确排除的品牌
   - 参数：内存/重量等是否满足用户明确要求
2. 理由一致性(level=soft)：推荐理由声称的属性，是否和商品实际 attributes 吻合？（防 LLM 编造/幻觉）
   例如理由说"32G 内存"但商品实际是 16G，记为问题并给出 product_id。
3. 多样性(level=soft)：3 款推荐是否过于同质（如全部同品牌、同内存、同定位）？适当多样更好。

规则：
1. 只有硬约束不满足或理由严重失实，pass 才为 false。
2. 小瑕疵记 soft，不否定整体推荐。
3. 只输出 JSON，不要解释文字。
"""


def review_recommendation(slots: dict, ranked: list, candidates: list) -> dict:
    """评审 Agent 校验推荐结果。返回 {pass, issues}。"""
    slots_json = json.dumps(slots, ensure_ascii=False)
    ranked_json = json.dumps(
        [
            {"id": r.get("id"), "title": r.get("title"), "price": float(r.get("price", 0)),
             "attributes": r.get("attributes", {}), "reason": r.get("reason", "")}
            for r in ranked
        ],
        ensure_ascii=False,
    )
    cand_ids = [p.get("id") for p in candidates]
    user = f"用户需求：{slots_json}\n候选商品 id：{cand_ids}\n最终推荐：{ranked_json}"
    return _json(REVIEW_SYSTEM, user)
