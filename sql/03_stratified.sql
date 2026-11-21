-- 分层加权（直接标准化）
-- 目标：控制地区构成后，延迟造成的评分落差是多少
-- 结果：1.73（粗效应）→ 1.63（加权后），仅下降 5.6%

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

-- 对照：粗效应（不分组直接比均值）
SELECT
    ROUND(AVG(CASE WHEN is_late = 0 THEN review_score END)
        - AVG(CASE WHEN is_late = 1 THEN review_score END), 3) AS crude_gap
FROM wide_orders_native
WHERE is_delivered = 1
  AND is_late IS NOT NULL
  AND review_score IS NOT NULL;
