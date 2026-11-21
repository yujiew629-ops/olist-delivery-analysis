-- ============================================================
-- Olist 电商宽表构建
-- 引擎：DuckDB（可直接读 CSV）
-- 输出粒度：一行 = 一个订单
--
-- 设计要点（这四条是建宽表的核心，面试必问）：
--   1. 粒度定死：以 orders 为事实表，一单一行，任何 join 都不能改变行数
--   2. 先聚合后 join：明细表（商品/支付/评价）先压到 order_id 粒度再关联，
--      否则一对多 join 会把订单数放大（最容易犯的错）
--   3. 一人多单：客户表 customer_id 每单唯一，必须用 customer_unique_id 才代表"人"
--   4. 多值取主：一单多商品取金额最大的品类作主品类；多次支付取金额最大的方式；
--      多条评价取最新一条
-- ============================================================

-- ---------- 0. 读原始文件 ----------
CREATE OR REPLACE VIEW raw_orders AS
SELECT * FROM read_csv_auto('data/raw/olist_orders_dataset.csv', header = true);

CREATE OR REPLACE VIEW raw_customers AS
SELECT * FROM read_csv_auto('data/raw/olist_customers_dataset.csv', header = true);

CREATE OR REPLACE VIEW raw_items AS
SELECT * FROM read_csv_auto('data/raw/olist_order_items_dataset.csv', header = true);

CREATE OR REPLACE VIEW raw_payments AS
SELECT * FROM read_csv_auto('data/raw/olist_order_payments_dataset.csv', header = true);

CREATE OR REPLACE VIEW raw_reviews AS
SELECT * FROM read_csv_auto('data/raw/olist_order_reviews_dataset.csv', header = true);

CREATE OR REPLACE VIEW raw_products AS
SELECT * FROM read_csv_auto('data/raw/olist_products_dataset.csv', header = true);

-- 品类葡→英对照（可选，展示时用英文品类更直观）
CREATE OR REPLACE VIEW raw_category_trans AS
SELECT * FROM read_csv_auto('data/raw/product_category_name_translation.csv', header = true);


-- ---------- 1. 商品明细 → 订单粒度 ----------
-- 一单可含多个商品行，这里压成一行，并挑出"主品类"
WITH items_ranked AS (
    SELECT
        i.order_id,
        i.order_item_id,
        i.product_id,
        i.seller_id,
        i.price,
        i.freight_value,
        COALESCE(p.product_category_name, 'unknown') AS category,
        -- 按金额倒序排名，第 1 名就是主品类
        ROW_NUMBER() OVER (
            PARTITION BY i.order_id
            ORDER BY i.price DESC, i.order_item_id
        ) AS rn
    FROM raw_items i
    LEFT JOIN raw_products p ON p.product_id = i.product_id
),
items_agg AS (
    SELECT
        order_id,
        COUNT(*)                        AS n_items,        -- 商品件数
        COUNT(DISTINCT product_id)      AS n_products,     -- 不同商品数
        COUNT(DISTINCT seller_id)       AS n_sellers,      -- 涉及几个卖家
        COUNT(DISTINCT category)        AS n_categories,   -- 涉及几个品类
        SUM(price)                      AS gmv,            -- 商品金额
        SUM(freight_value)              AS freight,        -- 运费
        MAX(CASE WHEN rn = 1 THEN category END) AS main_category  -- 主品类（金额最大）
    FROM items_ranked
    GROUP BY order_id
),


-- ---------- 2. 支付明细 → 订单粒度 ----------
pay_agg AS (
    SELECT
        order_id,
        COUNT(*)                                    AS n_payments,
        SUM(payment_value)                          AS payment_total,
        MAX(payment_installments)                   AS max_installments,
        MAX_BY(payment_type, payment_value)         AS main_payment_type  -- 金额最大的支付方式
    FROM raw_payments
    GROUP BY order_id
),


-- ---------- 3. 评价 → 订单粒度 ----------
-- 一个订单可能有多条评价（用户改评），取最新一条
rev_ranked AS (
    SELECT
        order_id,
        review_score,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_creation_date DESC NULLS LAST,
                     review_answer_timestamp DESC NULLS LAST
        ) AS rn,
        COUNT(*) OVER (PARTITION BY order_id) AS n_reviews_total
    FROM raw_reviews
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
        -- 主键与客户
        o.order_id,
        o.customer_id,
        c.customer_unique_id,          -- ★ 代表"人"，做复购/留存必须用它
        c.customer_city,
        c.customer_state,

        -- 订单状态与时间戳
        o.order_status,
        o.order_purchase_timestamp   AS purchase_ts,
        o.order_approved_at          AS approved_ts,
        o.order_delivered_carrier_date AS carrier_ts,
        o.order_delivered_customer_date AS delivered_ts,
        o.order_estimated_delivery_date AS estimated_ts,

        -- 商品与金额
        i.n_items, i.n_products, i.n_sellers, i.n_categories,
        i.main_category,
        i.gmv, i.freight,
        (COALESCE(i.gmv, 0) + COALESCE(i.freight, 0)) AS order_amount,

        -- 支付
        p.n_payments, p.payment_total, p.max_installments, p.main_payment_type,

        -- 评价
        r.review_score, r.n_reviews

    FROM raw_orders o
    LEFT JOIN raw_customers c ON c.customer_id = o.customer_id
    LEFT JOIN items_agg     i ON i.order_id    = o.order_id
    LEFT JOIN pay_agg       p ON p.order_id    = o.order_id
    LEFT JOIN rev_agg       r ON r.order_id    = o.order_id
),


-- ---------- 5. 派生字段 ----------
wide_derived AS (
    SELECT
        *,
        -- 是否已送达：后续所有配送相关指标只在已送达订单上有定义
        CASE WHEN order_status = 'delivered' AND delivered_ts IS NOT NULL
             THEN 1 ELSE 0 END AS is_delivered,

        -- 配送天数：下单→签收
        DATEDIFF('day', purchase_ts, delivered_ts) AS delivery_days,

        -- 延迟天数：实际签收 - 承诺送达；>0 表示迟到
        DATEDIFF('day', estimated_ts, delivered_ts) AS delay_days,

        -- 是否有承诺送达时间（部分订单没有）
        CASE WHEN estimated_ts IS NOT NULL THEN 1 ELSE 0 END AS has_estimate,

        -- 是否延迟（仅对已送达且有承诺时间的有定义，否则为 NULL）
        CASE
            WHEN delivered_ts IS NULL OR estimated_ts IS NULL THEN NULL
            WHEN delivered_ts > estimated_ts THEN 1
            ELSE 0
        END AS is_late,

        -- 时间维度
        DATE_TRUNC('month', purchase_ts)             AS order_month,
        CAST(DATE_TRUNC('month', purchase_ts) AS DATE) AS order_ym,
        DAYOFWEEK(purchase_ts)                       AS order_dow,     -- 0=周日
        EXTRACT(hour FROM purchase_ts)               AS order_hour,
        CASE WHEN DAYOFWEEK(purchase_ts) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend,

        -- 评价维度
        CASE WHEN review_score IS NULL THEN 1 ELSE 0 END AS no_review,
        CASE WHEN review_score <= 2 THEN 1 ELSE 0 END     AS is_low_score,
        CASE WHEN review_score >= 4 THEN 1 ELSE 0 END     AS is_high_score

    FROM wide_base
),


-- ---------- 6. 客户层级特征（同一人的第几单） ----------
wide_final AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY purchase_ts
        ) AS customer_order_seq,          -- 该客户的第几单
        COUNT(*) OVER (
            PARTITION BY customer_unique_id
        ) AS customer_total_orders,       -- 该客户累计下单数
        CASE
            WHEN ROW_NUMBER() OVER (
                PARTITION BY customer_unique_id ORDER BY purchase_ts
            ) = 1 THEN 1 ELSE 0
        END AS is_first_order
    FROM wide_derived
)

SELECT * FROM wide_final;
