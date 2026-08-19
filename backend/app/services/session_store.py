"""会话状态存储（MySQL 持久化 + 内存热缓存）。

- 每次对话后 save() 写穿 MySQL：sessions(完整 state) + messages(增量消息)
- 历史会话可从库还原完整状态，支持"继续对话"
- 接口兼容原内存版：get_or_create / get 语义不变
"""
import json
import uuid
from dataclasses import dataclass, field

import pymysql

from app.core.config import settings


def _conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


# 合法用途白名单（归一化）：品类词不算用途，避免"笔记本"被填进 use_case
_USE_CASE_MAP = [
    ("写代码", ["写代码", "编程", "开发", "程序员", "docker", "跑容器", "写程序"]),
    ("办公", ["办公", "工作", "商务", "写文档", "出差", "通勤"]),
    ("日常", ["日常", "日常用", "日常使用", "随便用", "普通用"]),
    ("游戏", ["游戏", "打游戏", "开黑", "电竞", "steam"]),
    ("影音", ["影音", "看视频", "追剧", "看电影", "视频", "娱乐"]),
    ("剪辑", ["剪辑", "视频剪辑", "剪视频", "创作", "pr剪辑"]),
    ("设计", ["设计", "作图", "画图", "平面", "ps修图"]),
    ("学习", ["学习", "上网课", "考研", "网课", "学生"]),
    ("摄影", ["摄影", "修图", "拍照"]),
    ("送礼", ["送礼", "送礼物", "送人", "送女朋友", "送对象"]),
]
_CATEGORY_WORDS = ["笔记本", "电脑", "手机", "平板", "台式机", "laptop", "notebook", "phone", "数码"]


def normalize_use_case(raw) -> str | None:
    """把用户说的用途归一化到白名单。品类词/无法识别的一律忽略（返回 None）。"""
    if not raw:
        return None
    low = str(raw).strip().lower()
    if not low:
        return None
    for w in _CATEGORY_WORDS:
        if w in low:
            return None
    for std, keys in _USE_CASE_MAP:
        for k in keys:
            if k in low:
                return std
    return None


@dataclass
class SlotState:
    category: str | None = None        # 品类：笔记本 / 手机
    budget_min: float | None = None
    budget_max: float | None = None
    brand: str | None = None
    use_case: str | None = None
    params: dict = field(default_factory=dict)
    exclude: list = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "brand": self.brand,
            "use_case": self.use_case,
            "params": self.params,
            "exclude": self.exclude,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SlotState":
        s = cls()
        if not d:
            return s
        s.category = d.get("category")
        s.budget_min = d.get("budget_min")
        s.budget_max = d.get("budget_max")
        s.brand = d.get("brand")
        s.use_case = d.get("use_case")
        s.params = dict(d.get("params") or {})
        s.exclude = list(d.get("exclude") or [])
        s.note = d.get("note") or ""
        return s

    def merge(self, delta: dict) -> None:
        """应用意图抽取的增量。delta 里只有非空字段才覆盖。"""
        if delta.get("category"):
            cat = str(delta["category"]).lower()
            if "笔记本" in cat or "电脑" in cat or "laptop" in cat:
                self.category = "笔记本"
            elif "手机" in cat or "phone" in cat or "平板" in cat:
                self.category = "手机"
        bmin = delta.get("budget_min")
        bmax = delta.get("budget_max")
        if bmin is not None or bmax is not None:
            lo = float(bmin) if bmin is not None else self.budget_min
            hi = float(bmax) if bmax is not None else self.budget_max
            if bmax is not None and bmin is None and self.budget_min is not None and hi < self.budget_min:
                lo = None
            if lo is not None and hi is not None and lo == hi:
                lo = lo * 0.9
                hi = hi * 1.1
            self.budget_min = lo
            self.budget_max = hi
        if delta.get("brand"):
            self.brand = str(delta["brand"])
        if delta.get("use_case"):
            uc = normalize_use_case(delta["use_case"])
            if uc:
                self.use_case = uc
        if isinstance(delta.get("params"), dict):
            for k, v in delta["params"].items():
                self.params[k] = str(v)
        if isinstance(delta.get("exclude"), list):
            self.exclude.extend([str(x) for x in delta["exclude"]])
        if delta.get("note"):
            self.note += str(delta["note"])


@dataclass
class SessionState:
    session_id: str
    user_id: int | None = None        # 所属用户（登录后关联）
    title: str = "新对话"
    slots: SlotState = field(default_factory=SlotState)
    history: list = field(default_factory=list)
    shown_ids: list = field(default_factory=list)
    rejected_ids: list = field(default_factory=list)
    pending_exclude: list = field(default_factory=list)
    last_decision: dict | None = None
    turn_no: int = 0
    clarify_asked: int = 0
    _persisted_msgs: int = 0  # 已写库的消息数（非序列化）

    def to_db(self) -> dict:
        """序列化为 sessions.state 可存 JSON。"""
        return {
            "title": self.title,
            "slots": self.slots.to_dict(),
            "history": self.history,
            "shown_ids": self.shown_ids,
            "rejected_ids": self.rejected_ids,
            "pending_exclude": self.pending_exclude,
            "last_decision": self.last_decision,
            "turn_no": self.turn_no,
            "clarify_asked": self.clarify_asked,
        }

    @classmethod
    def from_db(cls, session_id: str, state: dict, user_id: int | None = None) -> "SessionState":
        s = cls(session_id=session_id, user_id=user_id)
        if not state:
            return s
        s.title = state.get("title") or "新对话"
        s.slots = SlotState.from_dict(state.get("slots"))
        s.history = list(state.get("history") or [])
        s.shown_ids = list(state.get("shown_ids") or [])
        s.rejected_ids = list(state.get("rejected_ids") or [])
        s.pending_exclude = list(state.get("pending_exclude") or [])
        s.last_decision = state.get("last_decision")
        s.turn_no = int(state.get("turn_no") or 0)
        s.clarify_asked = int(state.get("clarify_asked") or 0)
        s._persisted_msgs = len(s.history)
        return s


_store: dict[str, SessionState] = {}


def _db_session_id(session_key: str) -> int | None:
    """查 sessions.id（无则 None）。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sessions WHERE session_key=%s", (session_key,))
            row = cur.fetchone()
            return row["id"] if row else None
    finally:
        conn.close()


def _load_from_db(session_key: str) -> SessionState | None:
    """从库加载会话状态，无则 None。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state, user_id FROM sessions WHERE session_key=%s", (session_key,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not row.get("state"):
        return None
    state = row["state"]
    if isinstance(state, str):
        state = json.loads(state)
    return SessionState.from_db(session_key, state, row.get("user_id"))


def get_or_create(session_id: str | None, user_id: int | None = None) -> SessionState:
    """取会话；不存在则新建（可关联 user_id）。优先内存，其次库，最后新建。"""
    if not session_id:
        session_id = "s_" + uuid.uuid4().hex[:12]
    if session_id in _store:
        return _store[session_id]
    loaded = _load_from_db(session_id)
    if loaded is not None:
        _store[session_id] = loaded
        return loaded
    session = SessionState(session_id=session_id, user_id=user_id)
    _store[session_id] = session
    return session


def get(session_id: str) -> SessionState | None:
    """只读取会话（回放/画像用）。"""
    if session_id in _store:
        return _store[session_id]
    loaded = _load_from_db(session_id)
    if loaded is not None:
        _store[session_id] = loaded
    return loaded


def save(session: SessionState) -> None:
    """写穿：upsert sessions(含 user_id) + 追加增量消息。"""
    if not session.title or session.title == "新对话":
        # 用首条用户消息做标题
        for m in session.history:
            if m.get("role") == "user":
                session.title = m["content"][:20]
                break
    state_json = json.dumps(session.to_db(), ensure_ascii=False)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (session_key, user_id, title, status, state) VALUES (%s, %s, %s, 'active', %s) "
                "ON DUPLICATE KEY UPDATE user_id=COALESCE(VALUES(user_id), user_id), title=VALUES(title), state=VALUES(state)",
                (session.session_id, session.user_id, session.title, state_json),
            )
            conn.commit()
            sid = _db_session_id(session.session_id)
            # 增量消息（推荐卡片一并落库，切回历史会话时才能还原）
            new_msgs = session.history[session._persisted_msgs:]
            if new_msgs and sid is not None:
                for m in new_msgs:
                    cards = m.get("cards") or []
                    cur.execute(
                        "INSERT INTO messages (session_id, role, content, cards) VALUES (%s, %s, %s, %s)",
                        (sid, m.get("role", "user"), m.get("content", ""),
                         json.dumps(cards, ensure_ascii=False) if cards else None),
                    )
                conn.commit()
        session._persisted_msgs = len(session.history)
    finally:
        conn.close()


def list_sessions(user_id: int | None = None, limit: int = 50) -> list[dict]:
    """最近会话列表（置顶优先）。登录用户只看自己的；未登录看所有（历史演示）。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if user_id is not None:
                cur.execute(
                    "SELECT s.session_key, s.title, s.pinned, s.updated_at, "
                    "(SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS msg_count "
                    "FROM sessions s WHERE s.user_id=%s "
                    "ORDER BY s.pinned DESC, s.updated_at DESC LIMIT %s",
                    (user_id, limit),
                )
            else:
                cur.execute(
                    "SELECT s.session_key, s.title, s.pinned, s.updated_at, "
                    "(SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS msg_count "
                    "FROM sessions s ORDER BY s.pinned DESC, s.updated_at DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "session_id": r["session_key"],
            "title": r["title"],
            "pinned": bool(r.get("pinned")),
            "updated_at": r["updated_at"].strftime("%Y-%m-%d %H:%M") if r["updated_at"] else "",
            "msg_count": r["msg_count"],
        }
        for r in rows
    ]


class SessionError(Exception):
    pass


def get_title(session_key: str) -> str:
    """会话标题（分享页展示用）。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM sessions WHERE session_key=%s", (session_key,))
            row = cur.fetchone()
    finally:
        conn.close()
    return (row or {}).get("title") or "对话记录"


def _owned_session(cur, session_key: str, user_id: int | None) -> dict:
    """取会话并校验归属；越权或不存在直接抛错。"""
    cur.execute("SELECT id, user_id FROM sessions WHERE session_key=%s", (session_key,))
    row = cur.fetchone()
    if not row:
        raise SessionError("会话不存在")
    # 归属了用户的会话只能本人操作；未归属的（未登录时产生）放行
    if row["user_id"] is not None and row["user_id"] != user_id:
        raise SessionError("无权操作该会话")
    return row


def rename_session(session_key: str, title: str, user_id: int | None = None) -> str:
    title = (title or "").strip()[:100]
    if not title:
        raise SessionError("标题不能为空")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            _owned_session(cur, session_key, user_id)
            cur.execute("UPDATE sessions SET title=%s WHERE session_key=%s", (title, session_key))
        conn.commit()
    finally:
        conn.close()
    # 同步内存态，避免下次 save() 用旧标题覆盖
    if session_key in _store:
        _store[session_key].title = title
    return title


def pin_session(session_key: str, pinned: bool, user_id: int | None = None) -> bool:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            _owned_session(cur, session_key, user_id)
            cur.execute("UPDATE sessions SET pinned=%s WHERE session_key=%s",
                        (1 if pinned else 0, session_key))
        conn.commit()
    finally:
        conn.close()
    return pinned


def delete_session(session_key: str, user_id: int | None = None) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            row = _owned_session(cur, session_key, user_id)
            cur.execute("DELETE FROM session_slots WHERE session_id=%s", (row["id"],))
            cur.execute("DELETE FROM session_decisions WHERE session_id=%s", (row["id"],))
            cur.execute("DELETE FROM messages WHERE session_id=%s", (row["id"],))
            cur.execute("DELETE FROM sessions WHERE id=%s", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    _store.pop(session_key, None)


def get_messages(session_key: str) -> list[dict]:
    """某会话的消息列表（回放/前端加载），含推荐卡片。"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.role, m.content, m.cards, m.created_at FROM messages m "
                "JOIN sessions s ON m.session_id=s.id WHERE s.session_key=%s ORDER BY m.id",
                (session_key,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        cards = r.get("cards")
        if isinstance(cards, str):
            try:
                cards = json.loads(cards)
            except json.JSONDecodeError:
                cards = []
        out.append({
            "role": r["role"],
            "content": r["content"],
            "cards": cards or [],
            "created_at": r["created_at"].strftime("%H:%M") if r["created_at"] else "",
        })
    return out
