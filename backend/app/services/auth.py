"""用户认证：注册 / 登录 / JWT。

- 密码 bcrypt 哈希(已装,无新依赖)
- JWT(HS256)签名,payload 含 user_id,role,exp
- get_user_id_from_token 供各接口解析登录态
- require_merchant 供商家端接口做角色鉴权
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pymysql

from app.core.config import settings

ROLES = ("buyer", "merchant")


class AuthError(Exception):
    pass


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def register(username: str, password: str, nickname: str = "",
             role: str = "buyer", shop_name: str = "") -> dict:
    username = username.strip()
    if len(username) < 2 or len(password) < 4:
        raise AuthError("用户名至少2位，密码至少4位")
    if role not in ROLES:
        raise AuthError("角色只能是 buyer 或 merchant")
    shop_name = shop_name.strip()
    if role == "merchant":
        if not shop_name:
            raise AuthError("商家注册需要填写店铺名")
        nickname = nickname or shop_name
    else:
        shop_name = ""
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO users (username, password_hash, nickname, role, shop_name) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (username, pw_hash, nickname or username, role, shop_name),
                )
            except pymysql.IntegrityError:
                raise AuthError("用户名已存在")
            conn.commit()
            cur.execute(
                "SELECT id, username, nickname, role, shop_name FROM users WHERE username=%s",
                (username,),
            )
            user = cur.fetchone()
    finally:
        conn.close()
    return _public(user)


def login(username: str, password: str) -> dict:
    username = username.strip()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, nickname, role, shop_name, password_hash FROM users WHERE username=%s",
                (username,),
            )
            user = cur.fetchone()
    finally:
        conn.close()
    if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise AuthError("用户名或密码错误")
    token = _sign_token(user["id"], user["role"])
    return {"token": token, "user": _public(user)}


def get_user(user_id: int) -> dict | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, nickname, role, shop_name FROM users WHERE id=%s",
                (user_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return _public(row) if row else None


def _public(row: dict) -> dict:
    """对外暴露的用户字段（不含密码哈希）。"""
    return {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"],
        "role": row.get("role") or "buyer",
        "shop_name": row.get("shop_name") or "",
    }


def _sign_token(user_id: int, role: str = "buyer") -> str:
    payload = {
        "user_id": user_id,
        "role": role or "buyer",
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGO)


def _payload(token: str) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGO])
    except jwt.PyJWTError:
        return None


def get_user_id_from_token(token: str) -> int | None:
    """解析 JWT 返回 user_id；无效返回 None。"""
    payload = _payload(token)
    return payload.get("user_id") if payload else None


def get_role_from_token(token: str) -> str | None:
    """解析 JWT 返回角色；无效返回 None。"""
    payload = _payload(token)
    return payload.get("role", "buyer") if payload else None


def parse_bearer(authorization: str | None) -> str:
    """从 Authorization 头取出裸 token。"""
    return (authorization or "").removeprefix("Bearer ").strip()


def require_user(token: str) -> int:
    """要求登录态，未登录抛 AuthError（由路由转为 401）。"""
    uid = get_user_id_from_token(token)
    if uid is None:
        raise AuthError("请先登录")
    return uid


def require_merchant(token: str) -> int:
    """要求商家身份，返回 merchant 的 user_id。

    以数据库中的 role 为准（token 里的 role 只作快速判断），
    避免用户角色变更后旧 token 仍能访问商家接口。
    """
    uid = require_user(token)
    user = get_user(uid)
    if not user or user["role"] != "merchant":
        raise AuthError("仅商家可访问")
    return uid
