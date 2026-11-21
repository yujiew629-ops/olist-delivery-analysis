-- 按州看评分落差与延迟率
-- 口径：已送达 + 有承诺送达时间 + 有评分
-- 筛选：总订单 >= 300 且延迟订单 >= 30（保证两组样本量）

SELECT
    customer_state                                              AS state,
    COUNT(*)                                                    AS n_orders,
    SUM(is_late)                                                AS n_late,
    ROUND(AVG(is_late), 3)                                      AS late_rate,
    ROUND(AVG(CASE WHEN is_late = 0 THEN review_score END), 2)  AS ontime_avg,
    ROUND(AVG(CASE WHEN is_late = 1 THEN review_score END), 2)  AS late_avg,
    ROUND(AVG(CASE WHEN is_late = 0 THEN review_score END)
        - AVG(CASE WHEN is_late = 1 THEN review_score END), 2)  AS gap,
    ROUND(AVG(is_low_score), 3)                                 AS low_rate
FROM wide_orders_native
WHERE is_delivered = 1
  AND is_late IS NOT NULL
  AND review_score IS NOT NULL
GROUP BY customer_state
HAVING COUNT(*) >= 300
   AND SUM(is_late) >= 30
ORDER BY gap DESC;
