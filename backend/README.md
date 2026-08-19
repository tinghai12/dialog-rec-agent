# backend —— FastAPI 后端

## 启动

```bash
cd backend
pip install -r requirements.txt

# 复制环境变量模板，填上你的 LLM API Key
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

打开 http://127.0.0.1:8000/docs 查看接口文档。

## 目录结构

```
app/
  main.py          应用入口 + 路由注册
  core/config.py   配置(读取 .env)
  routers/         接口路由(chat / products / health)
  schemas/         Pydantic 请求/响应模型(下一步填充)
  services/        业务逻辑(对话编排/检索/重排，下一步填充)
  models/          SQLAlchemy ORM 模型(下一步填充)
```

## 现状

- [x] 应用骨架 + 统一响应 + CORS + 健康检查
- [x] /api/chat 对话编排(意图/槽位 → 澄清 → 召回 → LLM 重排 → 解释 → 反事实)
- [x] /api/products 商品接口(读样例商品库)
- [x] 对话状态机：追问 / 排除 / 换一批 / "为什么没推X"
- [x] LLM 失败自动降级为"过滤结果 + 无理由"，用户无感
- [x] ChromaDB + bge-m3 语义检索(装好依赖即启用，未装自动退化为关键词匹配)
- [ ] MySQL 商品/会话持久化(等队友数据格式)
- [ ] Redis 会话缓存
