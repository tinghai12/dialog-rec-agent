"""FastAPI 应用入口。

启动：
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import auth, cart, chat, favorites, health, merchant, products
from app.services.merchant import UPLOAD_DIR

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="基于大语言模型的对话式推荐智能体",
    version="0.1.0",
)

# 开发期放开跨域，方便前端本地联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一响应格式：{"code": 0, "message": "ok", "data": ...}


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(favorites.router)
app.include_router(merchant.router)

# 商家上传的商品主图（/static/uploads/xxx.png）
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(UPLOAD_DIR.parent)), name="static")


@app.get("/", tags=["root"])
def root():
    return ok({"service": settings.PROJECT_NAME, "status": "running"})
