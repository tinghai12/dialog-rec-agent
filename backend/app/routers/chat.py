"""对话接口。

POST /api/chat  {message, session_id} → 对话编排（登录用户带 token 关联 user_id）
GET /api/sessions / GET /api/sessions/{key}/messages → 历史会话
"""
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.services import auth, events, session_store
from app.services.orchestrator import handle_message

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    session_id: str | None = Field(None, description="会话ID，不传则新建")


@router.post("/chat")
def chat(req: ChatRequest, authorization: str | None = Header(None)):
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    result = handle_message(req.session_id, req.message, uid)
    # 对话中推荐出的卡片计入商家看板的曝光
    events.track(
        [c.get("id") for c in (result.get("cards") or [])],
        "recommend", uid, req.session_id or "",
    )
    return {"code": 0, "message": "ok", "data": result}


# ---- 历史会话 ----

@router.get("/sessions")
def sessions(limit: int = 50, authorization: str | None = Header(None)):
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    data = session_store.list_sessions(uid, limit)
    return {"code": 0, "message": "ok", "data": {"sessions": data}}


@router.get("/sessions/{session_key}/messages")
def session_messages(session_key: str):
    """会话消息（公开读，分享链接依赖此接口）。"""
    data = session_store.get_messages(session_key)
    return {"code": 0, "message": "ok", "data": {"messages": data, "title": session_store.get_title(session_key)}}


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


class PinRequest(BaseModel):
    pinned: bool


@router.patch("/sessions/{session_key}/title")
def rename_session(session_key: str, req: RenameRequest, authorization: str | None = Header(None)):
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    try:
        title = session_store.rename_session(session_key, req.title, uid)
    except session_store.SessionError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已重命名", "data": {"title": title}}


@router.patch("/sessions/{session_key}/pin")
def pin_session(session_key: str, req: PinRequest, authorization: str | None = Header(None)):
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    try:
        session_store.pin_session(session_key, req.pinned, uid)
    except session_store.SessionError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已置顶" if req.pinned else "已取消置顶", "data": {"pinned": req.pinned}}


@router.delete("/sessions/{session_key}")
def delete_session(session_key: str, authorization: str | None = Header(None)):
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    try:
        session_store.delete_session(session_key, uid)
    except session_store.SessionError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "已删除", "data": None}
