-- ============================================================
-- Olist 配送延迟分析：完整 SQL 流程
-- 环境：MySQL 8.0，表 wide_orders_native（41 字段，一行一订单）
-- 按顺序执行，每段独立可跑
-- ============================================================


-- ============================================================
-- 0. 差评率的两个口径（先定死分母）
-- ============================================================
-- 平台口径：差评 / 全部有评价订单
-- 分析口径：差评 / 已送达且有评价订单
-- 两者差 1.9 个百分点，差额来自未送达订单（差评率 78%）

SELECT
    CASE WHEN is_delivered = 1 THEN '已送达' ELSE '未送达' END AS grp,
    COUNT(*)                        AS n_orders,
    SUM(is_low_score)               AS n_low_score,
    ROUND(AVG(is_low_score), 4)     AS low_rate,
    ROUND(AVG(review_score), 3)     AS avg_score
FROM wide_orders_native
WHERE review_score IS NOT NULL
GROUP BY grp;


-- ============================================================
-- 1. 粗效应：1.73 分是怎么来的
-- ============================================================
SELECT
    is_late,
    COUNT(*)                     AS n_orders,
    SUM(review_score)            AS sum_score,
    ROUND(AVG(review_score), 4)  AS avg_score
FROM wide_orders_native
WHERE is_delivered = 1
  AND is_late IS NOT NULL
  AND review_score IS NOT NULL
GROUP BY is_late;

-- 单值版（结果 -1.7287）
SELECT ROUND(
           AVG(CASE WHEN is_late = 0 THEN review_score END)
         - AVG(CASE WHEN is_late = 1 THEN review_score END), 4) AS crude_gap
FROM wide_orders_native
WHERE is_delivered = 1
  AND is_late IS NOT NULL
  AND review_score IS NOT NULL;


-- ============================================================
-- 2. 按州：延迟率与评分落差
-- ============================================================
SELECT
    customer_state                                              AS state,
    COUNT(*)                                                    AS n_orders,
    SUM(is_late)                                                AS n_late,
    ROUND(AVG(is_late), 3)                                      AS late_rate,
    ROUND(AVG(CASE WHEN is_late = 0 THEN review_score END), 2)  AS ontime_avg,
    ROUND(AVG(CASE WHEN is_late = 1 THEN review_score END), 2)  AS late_avg,
    ROUND(AVG(CASE WHEN is_late = 0 THEN review_score END)
        - AVG(CASE WHEN is_late = 1 THEN review_score END), 2)  AS gap
FROM wide_orders_native
WHERE is_delivered = 1
  AND is_late IS NOT NULL
  AND review_score IS NOT NULL
GROUP BY customer_state
HAVING COUNT(*) >= 300
   AND SUM(is_late) >= 30
ORDER BY gap DESC;


-- ============================================================
-- 3. 分层加权：1.73 → 1.63
-- ============================================================
WITH state_gap AS (
    SELECT
        customer_state                                          AS state,
        COUNT(*)                                                AS n_orders,
        AVG(CASE WHEN is_late = 0 THEN review_score END)
            - AVG(CASE WHEN is_late = 1 THEN review_score END)  AS gap
    FROM wide_orders_native
    WHERE is_delivered = 1
      AND is_late IS NOT NULL
      AND review_score IS NOT NULL
    GROUP BY customer_state
    HAVING COUNT(*) >= 300
       AND SUM(is_late) >= 30
)
SELECT
    ROUND(SUM(n_orders * gap) / SUM(n_orders), 3) AS adjusted_gap,
    SUM(n_orders)                                 AS orders_covered,
    COUNT(*)                                      AS states_used
FROM state_gap;


-- ============================================================
-- 4. 平衡性检验：延迟组和准时组像不像
-- ============================================================
SELECT
    is_late,
    COUNT(*)                          AS n,
    ROUND(AVG(order_amount), 1)       AS avg_amount,
    ROUND(AVG(n_items), 2)            AS avg_items,
    ROUND(AVG(n_sellers), 2)          AS avg_sellers,
    ROUND(AVG(max_installments), 2)   AS avg_inst,
    ROUND(AVG(CASE WHEN review_score IS NOT NULL THEN 1 ELSE 0 END), 3) AS review_rate
FROM wide_orders_native
WHERE is_delivered = 1
  AND is_late IS NOT NULL
GROUP BY is_late;


-- ============================================================
-- 5. 剂量反应：配送天数分段
-- 要点：每个 WHEN 只判断上界，靠 CASE 顺序保证不重叠
-- ============================================================
SELECT
    CASE
        WHEN delivery_days <= 3  THEN '1_≤3天'
        WHEN delivery_days <= 7  THEN '2_4-7天'
        WHEN delivery_days <= 10 THEN '3_8-10天'
        WHEN delivery_days <= 14 THEN '4_11-14天'
        WHEN delivery_days <= 21 THEN '5_15-21天'
        WHEN delivery_days <= 30 THEN '6_22-30天'
        ELSE '7_>30天'
    END                             AS band,
    COUNT(*)                        AS n_orders,
    ROUND(AVG(delivery_days), 1)    AS avg_days,
    ROUND(AVG(review_score), 3)     AS avg_score,
    ROUND(AVG(is_low_score), 3)     AS low_score_rate
FROM wide_orders_native
WHERE is_delivered = 1
  AND review_score IS NOT NULL
GROUP BY band
ORDER BY band;


-- ============================================================
-- 6. 分段斜率：每多一天掉多少分
-- 用窗口函数 LAG 拿上一段的值
-- ============================================================
WITH band_stat AS (
    SELECT
        CASE
            WHEN delivery_days <= 3  THEN '1_≤3'
            WHEN delivery_days <= 7  THEN '2_4-7'
            WHEN delivery_days <= 10 THEN '3_8-10'
            WHEN delivery_days <= 14 THEN '4_11-14'
            WHEN delivery_days <= 21 THEN '5_15-21'
            WHEN delivery_days <= 30 THEN '6_22-30'
            ELSE '7_>30'
        END                          AS band,
        COUNT(*)                     AS n_orders,
        AVG(delivery_days)           AS avg_days,
        AVG(review_score)            AS avg_score
    FROM wide_orders_native
    WHERE is_delivered = 1
      AND review_score IS NOT NULL
    GROUP BY band
)
SELECT
    band,
    n_orders,
    ROUND(avg_days, 1)                                          AS avg_days,
    ROUND(avg_score, 3)                                         AS avg_score,
    ROUND(avg_days  - LAG(avg_days)   OVER (ORDER BY band), 1)  AS delta_days,
    ROUND(avg_score - LAG(avg_score)  OVER (ORDER BY band), 3)  AS delta_score,
    ROUND((avg_score - LAG(avg_score) OVER (ORDER BY band))
        / (avg_days  - LAG(avg_days)  OVER (ORDER BY band)), 4) AS slope_per_day
FROM band_stat
ORDER BY band;


-- ============================================================
-- 7. 帕累托：谁贡献了最多可挽回分数
-- 参照水平 4.265 = ≤14 天段平均分
-- ============================================================
WITH cells AS (
    SELECT
        customer_state,
        CASE
            WHEN delivery_days <= 21 THEN '5_15-21'
            WHEN delivery_days <= 30 THEN '6_22-30'
            ELSE '7_>30'
        END                     AS band,
        COUNT(*)                AS n,
        AVG(review_score)       AS avg_score
    FROM wide_orders_native
    WHERE is_delivered = 1
      AND review_score IS NOT NULL
      AND delivery_days > 14
    GROUP BY customer_state, band
),
scored AS (
    SELECT *,
           GREATEST(4.265 - avg_score, 0) * n AS recoverable
    FROM cells
),
ranked AS (
    SELECT *,
           SUM(recoverable) OVER () AS total,
           SUM(recoverable) OVER (
               ORDER BY recoverable DESC
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS cum
    FROM scored
)
SELECT
    customer_state,
    band,
    n,
    ROUND(avg_score, 2)                 AS avg_score,
    ROUND(recoverable, 0)               AS recoverable,
    ROUND(cum / total * 100, 1)         AS cum_pct
FROM ranked
ORDER BY recoverable DESC
LIMIT 20;


-- ============================================================
-- 8. 州优先级：资源该投到哪
-- ============================================================
WITH s AS (
    SELECT
        customer_state,
        COUNT(*)          AS n_over14,
        AVG(review_score) AS avg_score
    FROM wide_orders_native
    WHERE is_delivered = 1
      AND review_score IS NOT NULL
      AND delivery_days > 14
    GROUP BY customer_state
)
SELECT
    customer_state,
    n_over14,
    ROUND(avg_score, 2)                                 AS avg_score,
    ROUND(GREATEST(4.265 - avg_score, 0) * n_over14, 0) AS recoverable,
    ROUND(GREATEST(4.265 - avg_score, 0) * n_over14
        / SUM(GREATEST(4.265 - avg_score, 0) * n_over14) OVER () * 100, 1) AS share_pct
FROM s
ORDER BY recoverable DESC;


-- ============================================================
-- 9. 策略量化：两条策略能减多少差评
-- 策略A：15–21 天压回 14 天以内（目标差评率 9.0%）
-- 策略B：22 天以上主动补偿，假设挽回一半缺口
-- ============================================================
WITH b AS (
    SELECT
        CASE
            WHEN delivery_days <= 21 THEN '5_15-21'
            WHEN delivery_days <= 30 THEN '6_22-30'
            ELSE '7_>30'
        END                     AS band,
        COUNT(*)                AS n,
        AVG(is_low_score)       AS low_rate
    FROM wide_orders_native
    WHERE is_delivered = 1
      AND review_score IS NOT NULL
      AND delivery_days > 14
    GROUP BY band
)
SELECT
    SUM(CASE WHEN band = '5_15-21' THEN (low_rate - 0.09) * n ELSE 0 END)
        AS strategy_A_cut,
    SUM(CASE WHEN band IN ('6_22-30', '7_>30') THEN (low_rate - 0.09) * n * 0.5 ELSE 0 END)
        AS strategy_B_cut,
    SUM(CASE WHEN band = '5_15-21' THEN (low_rate - 0.09) * n ELSE 0 END)
  + SUM(CASE WHEN band IN ('6_22-30', '7_>30') THEN (low_rate - 0.09) * n * 0.5 ELSE 0 END)
        AS total_cut
FROM b;


-- ============================================================
-- 10. 2018 年 3 月的断点（按天）
-- ============================================================
SELECT
    DATE(purchase_ts)                    AS d,
    COUNT(*)                             AS n_orders,
    ROUND(AVG(is_late), 3)               AS late_rate,
    ROUND(AVG(review_score), 2)          AS avg_score
FROM wide_orders_native
WHERE purchase_ts >= '2018-03-01'
  AND purchase_ts <  '2018-04-01'
  AND is_delivered = 1
  AND is_late IS NOT NULL
GROUP BY DATE(purchase_ts)
ORDER BY d;
