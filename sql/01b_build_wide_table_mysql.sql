-- ============================================================
-- Olist 宽表构建（MySQL 8.0 版）
-- 前置：8 张原始表已导入 olist 库（用 03_load_to_mysql.py 完成）
-- 输出：wide_orders_native，一行 = 一个订单
--
-- 与 DuckDB 版的六处方言差异，见文件末尾注释
-- ============================================================

DROP TABLE IF EXISTS wide_orders_native;

CREATE TABLE wide_orders_native AS
WITH
-- ---------- 1. 商品明细 → 订单粒度 ----------
items_ranked AS (
    SELECT
        i.order_id,
        i.order_item_id,
        i.product_id,
        i.seller_id,
        i.price,
        i.freight_value,
        COALESCE(p.product_category_name, 'unknown') AS category,
        ROW_NUMBER() OVER (
            PARTITION BY i.order_id
            ORDER BY i.price DESC, i.order_item_id
        ) AS rn
    FROM order_items i
    LEFT JOIN products p ON p.product_id = i.product_id
),
items_agg AS (
    SELECT
        order_id,
        COUNT(*)                    AS n_items,
        COUNT(DISTINCT product_id)  AS n_products,
        COUNT(DISTINCT seller_id)   AS n_sellers,
        COUNT(DISTINCT category)    AS n_categories,
        SUM(price)                  AS gmv,
        SUM(freight_value)          AS freight,
        MAX(CASE WHEN rn = 1 THEN category END) AS main_category
    FROM items_ranked
    GROUP BY order_id
),

-- ---------- 2. 支付明细 → 订单粒度 ----------
-- MySQL 没有 MAX_BY，改用窗口函数挑出金额最大的那笔
pay_ranked AS (
    SELECT
        order_id,
        payment_type,
        payment_value,
        payment_installments,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY payment_value DESC, payment_sequential
        ) AS rn
    FROM order_payments
),
pay_agg AS (
    SELECT
        order_id,
        COUNT(*)                        AS n_payments,
        SUM(payment_value)              AS payment_total,
        MAX(payment_installments)       AS max_installments,
        MAX(CASE WHEN rn = 1 THEN payment_type END) AS main_payment_type
    FROM pay_ranked
    GROUP BY order_id
),

-- ---------- 3. 评价去重，取最新一条 ----------
-- MySQL 不支持 NULLS LAST，用 (col IS NULL) 升序把它排到最后
rev_ranked AS (
    SELECT
        order_id,
        review_score,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY (review_creation_date IS NULL),
                     review_creation_date DESC,
                     (review_answer_timestamp IS NULL),
                     review_answer_timestamp DESC
        ) AS rn,
        COUNT(*) OVER (PARTITION BY order_id) AS n_reviews_total
    FROM order_reviews
),
rev_agg AS (
    SELECT
        order_id,
        MAX(CASE WHEN rn = 1 THEN review_score END) AS review_score,
        MAX(n_reviews_total)                        AS n_reviews
    FROM rev_ranked
    GROUP BY order_id
),

-- ---------- 4. 主表关联 ----------
wide_base AS (
    SELECT
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        c.customer_city,
        c.customer_state,
        o.order_status,
        o.order_purchase_timestamp     AS purchase_ts,
        o.order_approved_at            AS approved_ts,
        o.order_delivered_carrier_date AS carrier_ts,
        o.order_delivered_customer_date AS delivered_ts,
        o.order_estimated_delivery_date AS estimated_ts,
        i.n_items, i.n_products, i.n_sellers, i.n_categories,
        i.main_category, i.gmv, i.freight,
        (COALESCE(i.gmv, 0) + COALESCE(i.freight, 0)) AS order_amount,
        p.n_payments, p.payment_total, p.max_installments, p.main_payment_type,
        r.review_score, r.n_reviews
    FROM orders o
    LEFT JOIN customers   c ON c.customer_id = o.customer_id
    LEFT JOIN items_agg   i ON i.order_id    = o.order_id
    LEFT JOIN pay_agg     p ON p.order_id    = o.order_id
    LEFT JOIN rev_agg     r ON r.order_id    = o.order_id
),

-- ---------- 5. 派生字段 ----------
wide_derived AS (
    SELECT
        *,
        CASE WHEN order_status = 'delivered' AND delivered_ts IS NOT NULL
             THEN 1 ELSE 0 END                          AS is_delivered,

        DATEDIFF(delivered_ts, purchase_ts)             AS delivery_days,
        DATEDIFF(delivered_ts, estimated_ts)            AS delay_days,

        CASE WHEN estimated_ts IS NOT NULL THEN 1 ELSE 0 END AS has_estimate,

        -- 未送达时给 NULL，不能给 0，否则会把"没送到"算成"准时"
        CASE
            WHEN delivered_ts IS NULL OR estimated_ts IS NULL THEN NULL
            WHEN delivered_ts > estimated_ts THEN 1
            ELSE 0
        END                                             AS is_late,

        DATE_FORMAT(purchase_ts, '%Y-%m-01')            AS order_month,
        CAST(DATE_FORMAT(purchase_ts, '%Y-%m-01') AS DATE) AS order_ym,
        DAYOFWEEK(purchase_ts) - 1                      AS order_dow,   -- 0=周日
        HOUR(purchase_ts)                               AS order_hour,
        CASE WHEN DAYOFWEEK(purchase_ts) IN (1, 7)
             THEN 1 ELSE 0 END                          AS is_weekend,

        CASE WHEN review_score IS NULL THEN 1 ELSE 0 END AS no_review,
        CASE WHEN review_score <= 2    THEN 1 ELSE 0 END AS is_low_score,
        CASE WHEN review_score >= 4    THEN 1 ELSE 0 END AS is_high_score
    FROM wide_base
),

-- ---------- 6. 客户层级特征 ----------
wide_seq AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id ORDER BY purchase_ts
        ) AS customer_order_seq,
        COUNT(*) OVER (
            PARTITION BY customer_unique_id
        ) AS customer_total_orders
    FROM wide_derived
)
SELECT
    *,
    CASE WHEN customer_order_seq = 1 THEN 1 ELSE 0 END AS is_first_order
FROM wide_seq;


-- ============================================================
-- 7. 修类型 + 建索引
--
-- 为什么要先 MODIFY：pandas 导入时把字符串列都建成了 TEXT，
-- 而 MySQL 不允许对 TEXT 直接建索引（报 1170 错），必须先转 VARCHAR。
-- 这也是为什么原来的 wide_orders 上那些索引可能都没建成。
-- ============================================================
ALTER TABLE wide_orders_native
    MODIFY order_id            VARCHAR(64)  NOT NULL,
    MODIFY customer_id         VARCHAR(64)  NOT NULL,
    MODIFY customer_unique_id  VARCHAR(64)  NOT NULL,
    MODIFY order_status        VARCHAR(32),
    MODIFY customer_city       VARCHAR(64),
    MODIFY customer_state      VARCHAR(8),
    MODIFY main_category       VARCHAR(128),
    MODIFY main_payment_type   VARCHAR(32);

ALTER TABLE wide_orders_native ADD PRIMARY KEY (order_id);
CREATE INDEX idx_wn_customer ON wide_orders_native (customer_unique_id);
CREATE INDEX idx_wn_state    ON wide_orders_native (customer_state);
CREATE INDEX idx_wn_month    ON wide_orders_native (order_ym);
CREATE INDEX idx_wn_late     ON wide_orders_native (is_late);


-- ============================================================
-- 8. 验收（三项都要对得上）
-- ============================================================
-- SELECT COUNT(*) AS 行数 FROM wide_orders_native;                    -- 期望 99441
-- SELECT SUM(is_delivered) AS 已送达,
--        ROUND(AVG(is_late), 4) AS 延迟率,                            -- 期望 0.0811
--        ROUND(AVG(review_score), 4) AS 平均分                        -- 期望 4.09
-- FROM wide_orders_native;
--
-- SELECT '旧表(parquet)' AS 来源, COUNT(*) AS 行数,
--        ROUND(AVG(review_score), 4) AS 平均分 FROM wide_orders
-- UNION ALL
-- SELECT '新表(mysql)', COUNT(*), ROUND(AVG(review_score), 4) FROM wide_orders_native;


-- ============================================================
-- 与 DuckDB 版的六处方言差异
-- ------------------------------------------------------------
-- 1. 读文件
--    DuckDB: read_csv_auto('x.csv')
--    MySQL : 必须先建表再 LOAD DATA（本项目已用 Python 导入，跳过）
--
-- 2. 日期差
--    DuckDB: DATEDIFF('day', a, b)   ← 第一个参数是单位
--    MySQL : DATEDIFF(a, b)          ← 固定按天，无单位参数
--
-- 3. 取最大值对应的另一列
--    DuckDB: MAX_BY(payment_type, payment_value)
--    MySQL : 无此函数，用 ROW_NUMBER() 窗口函数取 rn=1
--
-- 4. 空值排序
--    DuckDB: ORDER BY col DESC NULLS LAST
--    MySQL : 不支持 NULLS LAST，用 ORDER BY (col IS NULL), col DESC
--
-- 5. 按月截断
--    DuckDB: DATE_TRUNC('month', ts)
--    MySQL : DATE_FORMAT(ts, '%Y-%m-01')
--
-- 6. 索引
--    DuckDB: 列存，索引不是必需
--    MySQL : TEXT 列不能直接建索引，要转 VARCHAR
-- ============================================================
