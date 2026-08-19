"""文本向量化（bge-m3，本地 CPU）。

模型首次使用会下载（约 2GB），之后缓存。加载失败抛异常，由 vector_store 捕获降级。
"""
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        from app.core.config import settings

        _model = SentenceTransformer(settings.EMBEDDING_MODEL, device=settings.EMBEDDING_DEVICE)
    return _model


def embed(texts: list[str]):
    model = get_model()
    return model.encode(texts, normalize_embeddings=True)
