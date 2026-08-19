"""认证接口：注册 / 登录 / 当前用户。"""
from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: str = ""
    role: str = "buyer"
    shop_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(req: RegisterRequest):
    try:
        user = auth.register(req.username, req.password, req.nickname, req.role, req.shop_name)
    except auth.AuthError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "注册成功", "data": user}


@router.post("/login")
def login(req: LoginRequest):
    try:
        data = auth.login(req.username, req.password)
    except auth.AuthError as e:
        return {"code": 1, "message": str(e)}
    return {"code": 0, "message": "登录成功", "data": data}


@router.get("/me")
def me(authorization: str | None = Header(None)):
    uid = auth.get_user_id_from_token(auth.parse_bearer(authorization))
    if uid is None:
        return {"code": 1, "message": "未登录"}
    user = auth.get_user(uid)
    return {"code": 0, "message": "ok", "data": user}
