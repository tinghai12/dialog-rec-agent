"""LLM 用户模拟器评测 + 消融实验。

评估"主动澄清"对推荐效果的价值，产出量化指标（答辩/简历核心证据）。

设计：
- 从商品库抽 N 个目标商品作为 persona（固定 seed 可复现）
- DeepSeek 扮演"有需求的用户"与系统真实对话（不告诉它目标商品，防作弊）
- 命中判定程序化：系统推荐卡片 id 是否包含目标商品 id
- 三组对比：
  A 有澄清 —— 系统主动追问补齐信息再推荐
  B 无澄清 —— 系统基于首句直接推荐（monkeypatch 关闭追问）
  C 热门榜 —— 按销量排序 Top-3，不对话

指标：Success@3（Top-3 含目标占比）、平均轮次、平均澄清次数

用法（在 backend 目录下）：
    python ../scripts/eval_simulator.py --personas 30 --seed 42
"""
import argparse
import json
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import app.services.orchestrator as O  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import catalog, llm  # noqa: E402

# 成本控制：评测批量跑时关闭评审 Agent（只影响展示，不影响 Success@3 指标）
settings.ENABLE_REVIEW = False

MAX_TURNS = 6
_ORIG_MISSING_CRITICAL = O._missing_critical

# 模拟器的系统提示：扮演有需求的用户，按 persona 特征表达需求
SIM_SYSTEM = """你是购物用户模拟器。扮演一位真实买家，在对话式推荐系统中选购商品。

你的画像（只按画像表达需求，绝不要直接报出"具体商品名"）：
{persona}

规则：
1. 像真实用户一样自然表达需求：用途、预算、偏好。系统问什么就答什么，语气口语化。
2. 如果系统推荐的商品你都不满意（偏离你的需求），可以表达不满并补充/强调你的要求（如"预算没那么高""要轻一点""换个别的看看"），或说"换一批"。
3. 如果系统推荐基本符合你的需求，就明确说"这款可以""就它吧"表示接受。
4. 不要编造画像里没有的信息，不要泄露"你心里想买的具体商品型号"。
5. 系统给出推荐列表时，直接点评是否满足你的需求（看配置/价格是否合适），不要反问系统"推荐了哪些"。
6. 只输出你的回复内容，不要任何额外解释。
"""


def build_personas(n: int, seed: int) -> list[dict]:
    """从商品库抽 n 个目标商品，构造 persona。"""
    rng = random.Random(seed)
    products = catalog.get_all()
    targets = rng.sample(products, min(n, len(products)))
    personas = []
    for p in targets:
        price = float(p["price"])
        personas.append({
            "target_id": p["id"],
            "target_title": p["title"],
            "category": p["category"],
            "use_case": _infer_use_case(p),
            "budget": int(round(price)),
            "persona_text": _persona_text(p),
        })
    return personas


def _infer_use_case(p: dict) -> str:
    """根据商品属性推断一个合理用途。"""
    if p["category"] == "手机":
        return "日常使用"
    attrs = p.get("attributes", {})
    gpu = str(attrs.get("显卡", ""))
    ram = str(attrs.get("内存", ""))
    if "独立" in gpu or "RTX" in gpu:
        return "打游戏"
    if "32" in ram or "64" in ram:
        return "写代码"
    return "办公"


def _persona_text(p: dict) -> str:
    price = float(p["price"])
    uc = _infer_use_case(p)
    attrs = p.get("attributes", {})
    weight = str(attrs.get("重量", ""))
    ram = str(attrs.get("内存", ""))
    prefs = []
    if weight:
        prefs.append(f"希望尽量轻便（{weight}以内）")
    if ram:
        prefs.append(f"内存至少{ram}")
    pref_str = "，".join(prefs) if prefs else "没有特别参数要求"
    return (
        f"你想买一台{p['category']}，主要用来{uc}，预算大概{price:.0f}元。{pref_str}。"
    )


def _simulate_reply(persona: dict, system_reply: str, history: list, cards: list | None = None) -> str:
    """模拟器回应系统的上一条消息（追问或推荐）。"""
    hist = json.dumps(history[-4:], ensure_ascii=False)
    rec = ""
    if cards:
        rec = "\n系统给你推荐的商品（你的视角）：\n" + json.dumps(
            [
                {"title": c.get("title"), "price": c.get("price"),
                 "attributes": c.get("attributes", {}), "reason": c.get("reason", "")}
                for c in cards[:3]
            ],
            ensure_ascii=False,
        )
    user = (
        f"对话历史（你与系统的对话）：{hist}\n"
        f"系统刚刚说：{system_reply}\n"
        f"{rec}\n"
        f"请你作为用户回应这句话。"
    )
    return llm._post(SIM_SYSTEM.format(persona=persona["persona_text"]), user,
                     temperature=0.7, max_tokens=200)


def run_persona(persona: dict, with_clarify: bool) -> dict:
    """跑一个 persona 的完整对话，返回 {success, turns, clarified}。"""
    session_id = None
    turns = 0
    clarified = 0
    history = []
    sim_reply = None

    # 无澄清组：关掉追问逻辑，系统基于首句直接推荐
    if not with_clarify:
        O._missing_critical = lambda s: []
    try:
        for _ in range(MAX_TURNS):
            if turns == 0:
                # 冷启动：首句只给品类，信息靠系统澄清补齐（测澄清价值）
                user_msg = f"我想买个{persona['category']}"
            else:
                user_msg = sim_reply

            resp = O.handle_message(session_id, user_msg)
            session_id = resp.get("session_id")
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": resp.get("reply", "")})
            turns += 1

            if resp.get("needs_more"):
                clarified += 1
                try:
                    sim_reply = _simulate_reply(persona, resp.get("reply", ""), history)
                except Exception:
                    sim_reply = "随便吧，你看着推荐"
                continue

            # 有推荐 → 程序化判定命中
            cards = resp.get("cards", [])
            hit = any(c["id"] == persona["target_id"] for c in cards)
            if hit:
                return {"success": True, "turns": turns, "clarified": clarified}
            # 未命中 → 模拟器表达不满（看到推荐卡片直接点评），最多跑满 MAX_TURNS
            try:
                sim_reply = _simulate_reply(persona, resp.get("reply", ""), history, cards)
            except Exception:
                sim_reply = "都不太合适，换一批吧"

        return {"success": False, "turns": turns, "clarified": clarified}
    finally:
        O._missing_critical = _ORIG_MISSING_CRITICAL


def baseline_hot(persona: dict) -> dict:
    """C 组：热门榜。按销量排序取 Top-3（无对话）。"""
    products = sorted(catalog.get_all(), key=lambda p: -(p.get("sales_30d") or 0))
    top3 = products[:3]
    hit = any(p["id"] == persona["target_id"] for p in top3)
    return {"success": hit, "turns": 1, "clarified": 0}


def summarize(results: list[dict]) -> dict:
    n = len(results)
    succ = sum(1 for r in results if r["success"])
    turns = [r["turns"] for r in results]
    clar = [r["clarified"] for r in results]
    return {
        "n": n,
        "success@3": round(succ / n, 3),
        "avg_turns": round(sum(turns) / n, 2),
        "avg_clarify": round(sum(clar) / n, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", type=int, default=30)
    ap.add_argument("--seeds", type=str, default="42", help="逗号分隔的多个 seed，如 42,7,123")
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",")]

    # 评测指标只看 Success@3/轮次，评审 Agent 不影响命中，跳过以降低成本
    O.llm.review_recommendation = lambda *a, **k: {"pass": True, "issues": []}

    per_seed = []
    for seed in seeds:
        personas = build_personas(args.personas, seed)
        print(f"\n=== seed {seed}: {len(personas)} 个 persona ===", flush=True)
        group_a, group_b, group_c = [], [], []
        for i, p in enumerate(personas, 1):
            print(f"  [{i}/{len(personas)}] {p['target_title'][:20]}", flush=True)
            group_a.append(run_persona(p, with_clarify=True))
            group_b.append(run_persona(p, with_clarify=False))
            group_c.append(baseline_hot(p))
        per_seed.append({
            "seed": seed,
            "a": summarize(group_a), "b": summarize(group_b), "c": summarize(group_c),
        })

    def agg(key):
        vals = [ps[key]["success@3"] for ps in per_seed]
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        return mean, std

    am, as_ = agg("a")
    bm, bs = agg("b")
    cm, cs = agg("c")

    print("\n" + "=" * 66)
    print(f"评测结果（{len(seeds)} 个 seed，每个 {args.personas} persona，Success@3 均值±标准差）")
    print("=" * 66)
    print(f"{'组别':<14}{'Success@3(均值±std)':<22}{'平均轮次':<10}{'平均澄清':<10}")
    print(f"{'A 有澄清':<12}{am:.3f}±{as_:.3f}    {per_seed[0]['a']['avg_turns']:<10}{per_seed[0]['a']['avg_clarify']:<10}")
    print(f"{'B 无澄清':<12}{bm:.3f}±{bs:.3f}    {per_seed[0]['b']['avg_turns']:<10}{per_seed[0]['b']['avg_clarify']:<10}")
    print(f"{'C 热门榜':<12}{cm:.3f}±{cs:.3f}    {per_seed[0]['c']['avg_turns']:<10}{per_seed[0]['c']['avg_clarify']:<10}")

    def _pct(gain_val):
        return "N/A(基线为0)" if gain_val is None else f"{gain_val*100:.0f}%"
    gain = None if cm == 0 else (am - cm) / cm
    gain_ab = None if bm == 0 else (am - bm) / bm
    print(f"\n结论：有澄清比热门榜 Success@3 提升 {_pct(gain)}")
    print(f"结论：有澄清比无澄清 Success@3 提升 {_pct(gain_ab)}")

    # 存 JSON
    out = {
        "meta": {"personas": args.personas, "seeds": seeds, "max_turns": MAX_TURNS},
        "per_seed": per_seed,
        "agg": {
            "A_clarify": {"mean": round(am, 3), "std": round(as_, 3)},
            "B_no_clarify": {"mean": round(bm, 3), "std": round(bs, 3)},
            "C_hot_rank": {"mean": round(cm, 3), "std": round(cs, 3)},
        },
        "gain_vs_baseline": gain,
        "gain_vs_no_clarify": gain_ab,
    }
    out_path = BACKEND.parent / "data" / "processed" / "eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {out_path}")


if __name__ == "__main__":
    main()
