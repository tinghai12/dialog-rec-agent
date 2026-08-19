# frontend —— Vue3 前端

## 启动

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 。开发期 `/api` 请求会自动代理到后端 `127.0.0.1:8000`。

## 目录结构

```
src/
  main.js         应用入口(element-plus / router)
  router/         路由(聊天页 / 后台)
  api/            后端接口封装(axios)
  views/          页面(ChatView / AdminView)
```

## 现状

- [x] Vite + Vue3 + Element Plus 骨架
- [x] 聊天页(调 /api/chat 占位接口)
- [ ] 商品卡片(含理由/缺点)
- [ ] 对比演示页
- [ ] 后台:会话记录/商品管理/雷达图
