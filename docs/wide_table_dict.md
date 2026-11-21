# 宽表字段说明

共 99,441 行 × 41 列

| 字段 | 中文 | 说明 |
|---|---|---|
| `order_id` | 订单主键 | 一个订单一行 |
| `customer_id` | 下单编号 | ★ 每单唯一，**不能**用来识别同一个人 |
| `customer_unique_id` | 客户唯一编号 | ★ 代表真实的人，复购/留存必须用它 |
| `customer_city / customer_state` | 客户城市 / 州 | 巴西 27 个州 |
| `order_status` | 订单状态 | delivered 占 97% |
| `purchase_ts` | 下单时间 | 分析基准时间 |
| `delivered_ts` | 实际签收时间 | 未送达为空 |
| `estimated_ts` | 承诺送达时间 | 平台给的预计日期 |
| `is_delivered` | 是否已送达 | 1/0，配送指标只在此为 1 时有定义 |
| `delivery_days` | 配送天数 | 下单→签收 |
| `delay_days` | 延迟天数 | 签收−承诺，>0 即迟到 |
| `has_estimate` | 有无承诺时间 | 1/0 |
| `is_late` | 是否延迟 | 1=迟到，0=准时，NULL=未送达 |
| `n_items` | 商品件数 | 一单可多件 |
| `n_products / n_sellers / n_categories` | 商品数 / 卖家数 / 品类数 | 衡量订单复杂度 |
| `main_category` | 主品类 | 按金额最大挑出，一单一个 |
| `gmv` | 商品金额 | 不含运费 |
| `freight` | 运费 | 占销售额约 16.6% |
| `order_amount` | 订单总金额 | 商品金额 + 运费 |
| `n_payments` | 支付笔数 | 一单可分多次支付 |
| `payment_total` | 支付总额 | 与 order_amount 基本相等 |
| `max_installments` | 最大分期数 | 巴西分期文化 |
| `main_payment_type` | 主支付方式 | 金额最大的那种 |
| `review_score` | 评分 | 1–5，多评价取最新一条 |
| `n_reviews` | 评价条数 | >1 说明用户改过评价 |
| `no_review / is_low_score / is_high_score` | 无评价 / 差评 / 好评 | 差评=≤2 星，好评=≥4 星 |
| `order_month / order_ym` | 下单月份 | 月度趋势用 order_ym |
| `order_dow / order_hour` | 星期几 / 小时 | 下单时段规律 |
| `is_weekend` | 是否周末 | 1/0 |
| `customer_order_seq` | 该客户第几单 | 1=首单 |
| `customer_total_orders` | 该客户累计下单数 | >1 即复购客户 |
| `is_first_order` | 是否首单 | 1/0 |