"""向量检索（ChromaDB + bge-m3）。

- 首次检索时把商品目录建立索引（embedding 一次，之后存磁盘）。
- embedder 加载失败时降级为关键词匹配，不影响主流程。
"""
from app.core.config import settings
from app.services import catalog


def _client():
    import chromadb

    client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
    return client.get_or_create_collection(
        name="products", metadata={"hnsw:space": "cosine"}
    )


def _embed(texts: list[str]):
    from app.services.embedder import embed

    return embed(texts)


def _desc(p: dict) -> str:
    attrs = " ".join(f"{k} {v}" for k, v in (p.get("attributes") or {}).items())
    reviews = " ".join((p.get("reviews") or [])[:2])
    return f"{p['title']} {p['brand']} {p['category']} {attrs} {' '.join(p.get('pros') or [])} {reviews}"


def ensure_index() -> None:
    """商品目录有变化时重建索引。"""
    products = catalog.get_all()
    col = _client()
    if col.count() >= len(products) and col.count() > 0:
        return
    col.delete(where={})  # 清空重建
    if not products:
        return
    ids = [str(p["id"]) for p in products]
    metadatas = [{"id": p["id"], "category": p["category"]} for p in products]
    docs = [_desc(p) for p in products]
    try:
        embeds = _embed(docs).tolist()
        col.add(ids=ids, documents=docs, embeddings=embeds, metadatas=metadatas)
    except Exception:
        # 无 embedding 能力时退化为存储文本，用向量库内置的近似匹配兜底
        col.add(ids=ids, documents=docs, metadatas=metadatas)


def search(query: str, top_k: int = 30) -> list[dict]:
    """语义检索，返回按相关度排序的商品。"""
    try:
        ensure_index()
        q = _embed([query])
        col = _client()
        hits = col.query(query_embeddings=q, n_results=top_k)
        ids = hits["ids"][0]
    except Exception:
        # 降级：关键词匹配
        ids = []
        keywords = [k for k in query.split() if len(k) > 1]
        scored = []
        for p in catalog.get_all():
            text = _desc(p)
            s = sum(1 for k in keywords if k in text)
            if s:
                scored.append((s, p["id"]))
        scored.sort(reverse=True)
        ids = [str(pid) for _, pid in scored[:top_k]]
    result = []
    for sid in ids:
        p = catalog.find_by_id(int(sid))
        if p:
            result.append(p)
    return result
