"""基于商品内容向量的相似商品推荐（ItemCF 的内容化变体）。

冷启动场景没有用户行为数据，无法做标准 ItemCF（买了A的用户也买了B），
故退而用商品内容特征（标题/属性/评论向量）构造相似度——等价于
ItemCF 的"内容化"版本：给用户当前关注的商品，推荐内容最相似的其他款。

答辩定位：这是"大模型 + 机器学习"中机器学习组件的落点（内容协同过滤）。
"""
from app.services import catalog, vector_store


def similar_by_id(product_id: int, top_k: int = 3) -> list[dict]:
    """返回与指定商品内容最相似的 top_k 款（排除自身）。"""
    p = catalog.find_by_id(product_id)
    if p is None:
        return []
    attrs = " ".join(f"{k} {v}" for k, v in (p.get("attributes") or {}).items())
    desc = f"{p['title']} {p['brand']} {p['category']} {attrs}"
    hits = vector_store.search(desc, top_k=top_k + 1)
    return [h for h in hits if h["id"] != product_id][:top_k]
