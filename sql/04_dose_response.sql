-- 剂量反应：配送天数分段 → 平均评分
-- 关键：CASE WHEN 每个分支只判断上界，靠顺序保证不重叠、不留缝
-- 结果：14 天内每天降 0.020 分，15 天起每天降 0.078 分（3.9 倍）

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

-- 说明：ELSE 兜住 >30 天。未送达订单已在 WHERE 中排除，
-- 故 delivery_days 不会为 NULL，不会落进 ELSE。
