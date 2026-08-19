# scripts —— 数据脚本

本目录放数据生成/入库/评测等脚本。当前为骨架，逐步填充：

| 脚本 | 用途 | 状态 |
|---|---|---|
| `generate_products.py` | 调 DeepSeek 批量生成商品 JSON（队友 A 用） | 待实现 |
| `import_products.py` | 把 JSON 导入 MySQL `products` 表 | 待实现 |
| `embed_products.py` | 商品向量化并写入 ChromaDB | 待实现 |
| `eval_simulator.py` | LLM 用户模拟器评测 + 消融 | 待实现 |

## 使用约定

- 敏感配置（API Key）不写死，放项目根 `.env` 或运行时传参。
- 生成结果统一输出到 `data/raw/`，处理后输出到 `data/processed/`。
- 详见各脚本头部的使用说明。
