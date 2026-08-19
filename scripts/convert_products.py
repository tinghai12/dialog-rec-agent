"""将队友生成的 items.json 转换为项目标准 products.json。

源数据：数据/data/out/items.json（500 款，队友生成）
目标：backend/app/data/products.json（catalog.py 加载的标准格式）

用法：
    python scripts/convert_products.py [源items.json路径]
"""
import json
import sys
from pathlib import Path

SRC_DEFAULT = Path(r"E:\project\企业实训\作业\大作业\数据\data\out\items.json")
DST = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "products.json"

# attributes_display 键 -> 中文键（供过滤与展示）
DISPLAY_MAP = {
    "ram": "内存",
    "storage": "硬盘",
    "weight": "重量",
    "screen": "屏幕",
}
# 从完整 attributes 补充的中文字段
EXTRA_MAP = {"cpu": "CPU", "gpu": "显卡"}


def convert(items):
    out = []
    for idx, it in enumerate(items, 1):
        disp = it.get("attributes_display") or {}
        attrs = {DISPLAY_MAP.get(k, k): v for k, v in disp.items()}
        full = it.get("attributes") or {}
        for ek, ck in EXTRA_MAP.items():
            if ek in full and ck not in attrs:
                attrs[ck] = str(full[ek])
        out.append({
            "id": idx,
            "item_id": it.get("item_id"),
            "title": it.get("title", ""),
            "brand": it.get("brand", ""),
            "category": "笔记本" if it.get("category") == "laptop" else "手机",
            "price": float(it.get("price", 0)),
            "attributes": attrs,
            "pros": [p["text"] for p in (it.get("pros") or [])],
            "cons": [c["text"] for c in (it.get("cons") or [])],
            "reviews": [r["content"] for r in (it.get("reviews") or [])],
        })
    return out


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC_DEFAULT
    items = json.loads(src.read_text(encoding="utf-8"))
    out = convert(items)
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"转换完成: {len(out)} 款 -> {DST}")
    print("示例:", json.dumps(out[0], ensure_ascii=False)[:200])


if __name__ == "__main__":
    main()
