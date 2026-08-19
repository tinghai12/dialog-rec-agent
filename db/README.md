# 数据库

本目录存放数据库相关脚本。

## 初始化

```bash
mysql -u root -p < db/schema.sql
```

执行后创建 `dialog_rec` 库和 5 张表：

- `products` 商品库（属性用 JSON）
- `sessions` 会话
- `messages` 对话消息
- `session_slots` 每轮槽位快照（画像雷达图数据源）
- `session_decisions` 每轮推荐决策（"为什么没推X" 与链路溯源数据源）

> 商品数据由 `scripts/` 下的生成脚本产出后导入 `products` 表。
