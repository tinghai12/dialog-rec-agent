"""生成商品数据 —— 占位。

计划：调用 DeepSeek 按批次生成 500+ 款商品 JSON（笔记本 + 手机），
每款含 title/brand/category/price/attributes/pros/cons/reviews，
输出到 data/raw/products/ 下，每款一个 JSON 文件。

实现依赖 LLM API key 与数据 schema（见 db/schema.sql 的 products 表）。

TODO(下一步)：
1. 读取 .env 的 LLM_API_KEY
2. 构造生成 prompt，分批请求，解析 JSON
3. 字段校验 + 去重 + 落盘
4. 生成一份 manifest，供人工抽查
"""
