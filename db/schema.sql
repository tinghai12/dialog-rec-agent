-- 对话式推荐智能体 —— 数据库 schema
-- MySQL 8.0，字符集 utf8mb4（支持中文 + emoji）
-- 说明：商品表用结构化 JSON 存 attributes；会话决策表支撑"为什么没推X"与回放

CREATE DATABASE IF NOT EXISTS dialog_rec DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE dialog_rec;

-- 用户表(买家与商家同表，用 role 区分)
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)   NOT NULL COMMENT '用户名',
    password_hash VARCHAR(200)  NOT NULL COMMENT 'bcrypt 密码哈希',
    nickname      VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '昵称',
    role          VARCHAR(20)   NOT NULL DEFAULT 'buyer' COMMENT '角色: buyer/merchant',
    shop_name     VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '店铺名(role=merchant 时有效)',
    warehouse_name    VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '仓库名(商家发货点)',
    warehouse_address VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '仓库地址',
    warehouse_lng     DECIMAL(10,6) NULL COMMENT '仓库经度',
    warehouse_lat     DECIMAL(10,6) NULL COMMENT '仓库纬度',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_username (username),
    KEY idx_role (role)
) ENGINE=InnoDB COMMENT='用户(买家/商家)';

-- 收藏表
CREATE TABLE IF NOT EXISTS favorites (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT        NOT NULL,
    product_id    BIGINT        NOT NULL,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_product (user_id, product_id),
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='收藏';

-- 商品表
CREATE TABLE IF NOT EXISTS products (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    title         VARCHAR(255)  NOT NULL COMMENT '商品标题',
    brand         VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '品牌',
    category      VARCHAR(50)   NOT NULL COMMENT '品类: 笔记本/手机',
    price         DECIMAL(10,2) NOT NULL COMMENT '价格(元)',
    attributes    JSON          NULL COMMENT '结构化属性 {ram, weight, screen...}',
    pros          JSON          NULL COMMENT '优点列表',
    cons          JSON          NULL COMMENT '缺点列表(供主动披露缺点)',
    reviews       JSON          NULL COMMENT '中文评论文本列表(供RAG/证据引用)',
    is_on_sale    TINYINT       NOT NULL DEFAULT 1 COMMENT '是否在售 0/1',
    -- ===== 归属商家 =====
    merchant_id   BIGINT        NULL          COMMENT '所属商家 users.id',
    shop_name     VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '店铺名(冗余,列表展示)',
    -- ===== 营销位(商家端可编辑) =====
    main_image        VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '主图URL(商家上传,空则前端用CSS海报兜底)',
    poster_bg         VARCHAR(60)   NOT NULL DEFAULT '' COMMENT '兜底海报底色主题 dark/blue/purple/red/green',
    poster_headline   VARCHAR(60)   NOT NULL DEFAULT '' COMMENT '海报主标语,如"超强芯生 高效出众"',
    poster_subline    VARCHAR(80)   NOT NULL DEFAULT '' COMMENT '海报副标语,如"低噪音不扰人"',
    poster_specs      JSON          NULL          COMMENT '海报规格浮层 ["R7 9800X3D","RTX 5070TI"]',
    poster_price_label VARCHAR(30)  NOT NULL DEFAULT '' COMMENT '浮层价格前缀,如"国补到手价"',
    promo_banner      VARCHAR(60)   NOT NULL DEFAULT '' COMMENT '促销条文案,如"天猫 七夕礼遇季"',
    promo_banner_style VARCHAR(20)  NOT NULL DEFAULT 'none' COMMENT '促销条样式 none/tmall/subsidy/live',
    title_prefix      VARCHAR(60)   NOT NULL DEFAULT '' COMMENT '标题前缀优惠,如"【24期免息】"',
    rank_label        VARCHAR(60)   NOT NULL DEFAULT '' COMMENT '榜单标签,如"办公台式机好评榜·第1名"',
    final_price       DECIMAL(10,2) NULL          COMMENT '到手价(空则用 price)',
    saved_amount      DECIMAL(10,2) NULL          COMMENT '已省/已补金额',
    installment       VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '分期,如"3期"/"12期"',
    service_tags      JSON          NULL          COMMENT '服务标签 ["退货宝","包邮"]',
    sold_count        INT           NOT NULL DEFAULT 0 COMMENT '付款人数',
    repeat_buyers     INT           NOT NULL DEFAULT 0 COMMENT '回头客人数',
    promo_start       DATETIME      NULL          COMMENT '活动开始',
    promo_end         DATETIME      NULL          COMMENT '活动结束',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_category_price (category, price),
    KEY idx_brand (brand),
    KEY idx_merchant (merchant_id)
) ENGINE=InnoDB COMMENT='商品库';

-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_key   VARCHAR(64)   NOT NULL COMMENT '前端生成的会话ID',
    user_id       BIGINT        NULL COMMENT '所属用户(登录后关联)',
    title         VARCHAR(100)  NOT NULL DEFAULT '新对话' COMMENT '会话标题(首条消息截断)',
    user_name     VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '用户标识(可选)',
    status        VARCHAR(20)   NOT NULL DEFAULT 'active' COMMENT 'active/ended',
    pinned        TINYINT       NOT NULL DEFAULT 0 COMMENT '是否置顶 0/1',
    state         JSON          NULL COMMENT '完整会话状态序列化(槽位/history/决策等)',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_session_key (session_key),
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='会话';

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id    BIGINT        NOT NULL,
    role          VARCHAR(20)   NOT NULL COMMENT 'user/assistant/system',
    content       TEXT          NOT NULL,
    cards         JSON          NULL COMMENT '该条回复附带的推荐卡片(供切回历史会话时还原)',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_session (session_id, created_at),
    CONSTRAINT fk_msg_session FOREIGN KEY (session_id) REFERENCES sessions(id)
) ENGINE=InnoDB COMMENT='对话消息';

-- 槽位快照表(每轮对话后的偏好状态，供画像雷达图/回放)
CREATE TABLE IF NOT EXISTS session_slots (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id    BIGINT        NOT NULL,
    turn_no       INT           NOT NULL COMMENT '第几轮',
    slots         JSON          NOT NULL COMMENT '当前槽位快照 {budget, use_case, ...}',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_session (session_id, turn_no),
    CONSTRAINT fk_slots_session FOREIGN KEY (session_id) REFERENCES sessions(id)
) ENGINE=InnoDB COMMENT='槽位快照';

-- 决策记录表(每次推荐的召回/淘汰/排序记录，供"为什么没推X"与链路溯源)
CREATE TABLE IF NOT EXISTS session_decisions (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id    BIGINT        NOT NULL,
    turn_no       INT           NOT NULL,
    query_slots   JSON          NOT NULL COMMENT '本轮槽位',
    recalled      JSON          NULL COMMENT '召回的候选列表',
    filtered_out  JSON          NULL COMMENT '被淘汰的候选及原因 [{id, reason}]',
    ranked        JSON          NULL COMMENT '最终排序结果',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_session (session_id, turn_no),
    CONSTRAINT fk_decisions_session FOREIGN KEY (session_id) REFERENCES sessions(id)
) ENGINE=InnoDB COMMENT='推荐决策记录';

-- 购物车表(按用户隔离)
CREATE TABLE IF NOT EXISTS cart_items (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT        NOT NULL COMMENT '所属用户',
    session_key   VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '来源会话(可选)',
    product_id    BIGINT        NOT NULL COMMENT '商品ID',
    quantity      INT           NOT NULL DEFAULT 1,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_product (user_id, product_id),
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='购物车';

-- 订单表(下单时快照商品信息)
CREATE TABLE IF NOT EXISTS orders (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_no      VARCHAR(32)   NOT NULL COMMENT '订单号',
    user_id       BIGINT        NOT NULL COMMENT '所属用户',
    merchant_id   BIGINT        NULL     COMMENT '所属商家(按商家拆单)',
    shop_name     VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '店铺名快照',
    session_key   VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '来源会话(可选)',
    products      JSON          NOT NULL COMMENT '商品快照 [{id,title,price,quantity}]',
    total_amount  DECIMAL(10,2) NOT NULL COMMENT '总金额',
    status        VARCHAR(20)   NOT NULL DEFAULT 'pending'
                  COMMENT 'pending待商家确认/confirmed已接单/shipping配送中/delivered已送达/cancelled已取消',
    -- ===== 收货信息(下单时从 addresses 快照) =====
    address_id    BIGINT        NULL     COMMENT '收货地址ID',
    receiver      VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '收货人',
    phone         VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '联系电话',
    address_text  VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '完整收货地址',
    dest_lng      DECIMAL(10,6) NULL     COMMENT '收货点经度',
    dest_lat      DECIMAL(10,6) NULL     COMMENT '收货点纬度',
    origin_lng    DECIMAL(10,6) NULL     COMMENT '发货点经度',
    origin_lat    DECIMAL(10,6) NULL     COMMENT '发货点纬度',
    origin_name   VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '发货点名称(商家仓库或同城前置仓)',
    warehouse_id  BIGINT        NULL     COMMENT '商家接单时选择的发货仓',
    -- ===== 配送轨迹 =====
    route         JSON          NULL     COMMENT '高德路径规划得到的道路点 [[lng,lat],...]',
    eta_minutes   INT           NOT NULL DEFAULT 30 COMMENT '预计配送总时长(分钟)',
    rider_name    VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '骑手姓名',
    rider_phone   VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '骑手电话',
    confirmed_at  DATETIME      NULL     COMMENT '商家接单时间',
    shipped_at    DATETIME      NULL     COMMENT '发货时间(配送进度按此计算)',
    delivered_at  DATETIME      NULL     COMMENT '送达时间',
    -- ===== 售后 =====
    aftersale_status VARCHAR(20) NOT NULL DEFAULT 'none'
                     COMMENT 'none/pending待处理/approved已同意/rejected已拒绝',
    aftersale_type   VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'refund退款/return退货/exchange换货/repair维修',
    aftersale_reason VARCHAR(255) NOT NULL DEFAULT '' COMMENT '售后原因',
    aftersale_reply  VARCHAR(255) NOT NULL DEFAULT '' COMMENT '商家处理说明',
    aftersale_at     DATETIME    NULL COMMENT '申请时间',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_no (order_no),
    KEY idx_user (user_id),
    KEY idx_merchant_status (merchant_id, status)
) ENGINE=InnoDB COMMENT='订单';

-- 收货地址表(用户长期登记，下单时快照到订单)
CREATE TABLE IF NOT EXISTS addresses (    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT        NOT NULL COMMENT '所属用户',
    receiver      VARCHAR(50)   NOT NULL COMMENT '收货人',
    phone         VARCHAR(20)   NOT NULL COMMENT '联系电话',
    province      VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '省',
    city          VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '市',
    district      VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '区/县',
    detail        VARCHAR(255)  NOT NULL COMMENT '详细地址',
    lng           DECIMAL(10,6) NULL     COMMENT '经度(高德地理编码)',
    lat           DECIMAL(10,6) NULL     COMMENT '纬度(高德地理编码)',
    is_default    TINYINT       NOT NULL DEFAULT 0 COMMENT '是否默认地址',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='收货地址';

-- 商家仓库(一个商家可有多个发货仓)
CREATE TABLE IF NOT EXISTS warehouses (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id   BIGINT        NOT NULL COMMENT '所属商家 users.id',
    name          VARCHAR(100)  NOT NULL COMMENT '仓库名',
    address       VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '仓库地址',
    lng           DECIMAL(10,6) NULL     COMMENT '经度',
    lat           DECIMAL(10,6) NULL     COMMENT '纬度',
    is_default    TINYINT       NOT NULL DEFAULT 0 COMMENT '是否主仓',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_merchant (merchant_id)
) ENGINE=InnoDB COMMENT='商家仓库';

-- 分仓库存(商家接单选仓时校验并扣减)
CREATE TABLE IF NOT EXISTS warehouse_stock (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id  BIGINT        NOT NULL,
    product_id    BIGINT        NOT NULL,
    quantity      INT           NOT NULL DEFAULT 0 COMMENT '剩余库存',
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_wh_product (warehouse_id, product_id),
    KEY idx_product (product_id)
) ENGINE=InnoDB COMMENT='分仓库存';

-- 用户画像缓存表(对话槽位→标签/雷达图，供跨会话记忆)
CREATE TABLE IF NOT EXISTS profiles (    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT        NOT NULL COMMENT '所属用户',
    session_key   VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '来源会话(可选)',
    slots         JSON          NULL COMMENT '槽位快照',
    tags          JSON          NULL COMMENT '画像标签',
    radar         JSON          NULL COMMENT '雷达图维度打分',
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user (user_id)
) ENGINE=InnoDB COMMENT='用户画像缓存';

-- 商品埋点事件表(供商家数据看板: 曝光/点击/加购/下单)
CREATE TABLE IF NOT EXISTS product_events (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id    BIGINT        NOT NULL COMMENT '商品ID',
    merchant_id   BIGINT        NULL     COMMENT '商品所属商家(冗余,便于按店铺聚合)',
    user_id       BIGINT        NULL     COMMENT '触发用户(未登录为空)',
    event_type    VARCHAR(20)   NOT NULL COMMENT 'recommend/view/cart/order',
    session_key   VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '来源会话(可选)',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_merchant_type (merchant_id, event_type),
    KEY idx_product_type (product_id, event_type),
    KEY idx_created (created_at)
) ENGINE=InnoDB COMMENT='商品埋点事件';
