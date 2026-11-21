"""第一步数据摸底：把业务事实摸清楚，再决定项目讲什么故事。

运行：
    python 01_data_profile.py          # 只看结论
    python 01_data_profile.py -v       # 附带中间细节

输出会写进 docs/data_profile.txt，作为项目 Stage 1 的交付物。
"""

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
RAW = BASE / "data" / "raw"
OUT = BASE / "docs" / "data_profile.txt"

lines: list[str] = []


def say(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def main() -> None:
    orders = pd.read_csv(
        RAW / "olist_orders_dataset.csv",
        parse_dates=[
            "order_purchase_timestamp",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    )
    cust = pd.read_csv(RAW / "olist_customers_dataset.csv")
    reviews = pd.read_csv(RAW / "olist_order_reviews_dataset.csv")
    items = pd.read_csv(RAW / "olist_order_items_dataset.csv")
    prods = pd.read_csv(RAW / "olist_products_dataset.csv")

    say("=" * 60)
    say("一、订单规模与时间范围")
    say("=" * 60)
    say(f"订单总数        : {len(orders):,}")
    say(
        f"下单时间范围    : {orders.order_purchase_timestamp.min():%Y-%m-%d} "
        f"→ {orders.order_purchase_timestamp.max():%Y-%m-%d}"
    )
    span = (
        orders.order_purchase_timestamp.max() - orders.order_purchase_timestamp.min()
    ).days
    say(f"跨度            : {span} 天（约 {span / 365:.1f} 年）")
    say("")
    say("订单状态分布（按占比排序）：")
    status = orders.order_status.value_counts()
    for k, v in status.items():
        say(f"  {k:<12} {v:>7,}  {v / len(orders):>6.2%}")
    delivered = status.get("delivered", 0)
    say("")
    say(f"→ 可用样本：delivered 订单 {delivered:,} 笔（{delivered / len(orders):.1%}）")

    say("")
    say("=" * 60)
    say("二、复购（决定项目能不能做用户留存）")
    say("=" * 60)
    merged = orders.merge(
        cust[["customer_id", "customer_unique_id"]], on="customer_id", how="left"
    )
    buyers = merged.customer_unique_id.nunique()
    order_cnt = merged.groupby("customer_unique_id").size()
    repeaters = int((order_cnt > 1).sum())
    say(f"下单客户数（去重）: {buyers:,}")
    say(f"其中复购人数      : {repeaters:,}")
    say(f"复购率            : {repeaters / buyers:.2%}")
    say(f"人均订单数        : {order_cnt.mean():.3f}")
    say("")
    say("订单数分布（每个客户下了几单）：")
    dist = order_cnt.value_counts().sort_index()
    for k, v in dist.items():
        if k > 5:
            break
        say(f"  {k} 单 : {v:>7,} 人  {v / buyers:>6.2%}")
    say(f"  >5 单: {int((order_cnt > 5).sum()):>7,} 人")
    say("")
    say("★ 关键判断：复购率只有 3% 左右，这是典型的【一次性消费为主】平台。")
    say("  含义 1：不能照搬「用户留存曲线」那套电商模板，留存会快速归零。")
    say("  含义 2：这本身就是第一个业务发现——「为什么几乎不复购」比")
    say("          「预测谁会复购」更有价值，也更像真实分析师会问的问题。")
    say("  含义 3：若做复购预测，正样本仅约 3%，必须处理极不平衡。")

    say("")
    say("=" * 60)
    say("三、评价（体验侧核心指标）")
    say("=" * 60)
    say(f"评价条数        : {len(reviews):,}（订单覆盖率 {reviews.order_id.nunique() / len(orders):.1%}）")
    say(f"平均评分        : {reviews.review_score.mean():.2f}")
    say("评分分布：")
    for k, v in reviews.review_score.value_counts().sort_index().items():
        bar = "█" * int(v / len(reviews) * 50)
        say(f"  {k} 星 : {v:>7,}  {v / len(reviews):>6.2%}  {bar}")
    low = (reviews.review_score <= 2).mean()
    say(f"差评率（≤2星）  : {low:.2%}")

    say("")
    say("=" * 60)
    say("四、配送时效（本项目最有价值的因果入口）")
    say("=" * 60)
    dlv = orders.dropna(
        subset=["order_delivered_customer_date", "order_estimated_delivery_date"]
    ).copy()
    dlv["is_late"] = (
        dlv.order_delivered_customer_date > dlv.order_estimated_delivery_date
    )
    dlv["days"] = (
        dlv.order_delivered_customer_date - dlv.order_purchase_timestamp
    ).dt.days
    say(f"有完整送达时间  : {len(dlv):,} 单")
    say(f"平均送达天数    : {dlv.days.mean():.1f} 天（中位 {dlv.days.median():.0f} 天）")
    say(f"延迟率          : {dlv.is_late.mean():.2%}")
    say("")
    joined = dlv.merge(reviews[["order_id", "review_score"]], on="order_id")
    late_avg = joined[joined.is_late].review_score.mean()
    ontime_avg = joined[~joined.is_late].review_score.mean()
    say(f"延迟订单均分    : {late_avg:.2f}")
    say(f"准时订单均分    : {ontime_avg:.2f}")
    say(f"差距            : {ontime_avg - late_avg:.2f} 分")
    say("")
    say("★ 这就是你的因果分析选题：延迟配送是否导致评分下降、是否抑制复购。")
    say("  注意：延迟和地区强相关（偏远州配送慢），直接比均值有混杂，")
    say("  需要控制州、品类、金额后再比较——这正是统计背景的用武之地。")

    say("")
    say("=" * 60)
    say("五、交易规模与商品")
    say("=" * 60)
    say(f"有商品的订单    : {items.order_id.nunique():,}")
    say(f"商品行数        : {len(items):,}（一单可多商品）")
    say(f"商品销售额合计  : {items.price.sum():,.0f} 雷亚尔")
    say(f"运费合计        : {items.freight_value.sum():,.0f} 雷亚尔"
        f"（占销售额 {items.freight_value.sum() / items.price.sum():.1%}）")
    say(f"品类数          : {prods.product_category_name.nunique()}（缺失 {prods.product_category_name.isna().sum()} 个商品）")

    say("")
    say("=" * 60)
    say("六、下一步要做的事")
    say("=" * 60)
    say("1. 定选题：走「首单体验 → 是否复购/是否差评」这条线，")
    say("   而不是套用通用的留存漏斗模板。")
    say("2. 建宽表：订单粒度，join 客户/商品/支付/评价/卖家/地理。")
    say("3. 处理缺失：delivered 之外的状态要标记，不要直接删。")
    say("4. 口径先定死：什么算「一次有效购买」、什么算「延迟」。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已写入 {OUT}")


if __name__ == "__main__":
    main()
