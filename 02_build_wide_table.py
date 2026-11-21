"""跑 SQL 建宽表，落盘为 parquet，并做四项体检。

运行：
    python 02_build_wide_table.py

产出：
    data/processed/orders_wide.parquet   宽表
    docs/wide_table_dict.md              字段说明
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
SQL_FILE = BASE / "sql" / "01_build_wide_table.sql"
OUT_PARQUET = BASE / "data" / "processed" / "orders_wide.parquet"
OUT_DICT = BASE / "docs" / "wide_table_dict.md"

# 字段说明（写进文档，面试时照着讲）
DICT = [
    ("order_id", "订单主键", "一个订单一行"),
    ("customer_id", "下单编号", "★ 每单唯一，**不能**用来识别同一个人"),
    ("customer_unique_id", "客户唯一编号", "★ 代表真实的人，复购/留存必须用它"),
    ("customer_city / customer_state", "客户城市 / 州", "巴西 27 个州"),
    ("order_status", "订单状态", "delivered 占 97%"),
    ("purchase_ts", "下单时间", "分析基准时间"),
    ("delivered_ts", "实际签收时间", "未送达为空"),
    ("estimated_ts", "承诺送达时间", "平台给的预计日期"),
    ("is_delivered", "是否已送达", "1/0，配送指标只在此为 1 时有定义"),
    ("delivery_days", "配送天数", "下单→签收"),
    ("delay_days", "延迟天数", "签收−承诺，>0 即迟到"),
    ("has_estimate", "有无承诺时间", "1/0"),
    ("is_late", "是否延迟", "1=迟到，0=准时，NULL=未送达"),
    ("n_items", "商品件数", "一单可多件"),
    ("n_products / n_sellers / n_categories", "商品数 / 卖家数 / 品类数", "衡量订单复杂度"),
    ("main_category", "主品类", "按金额最大挑出，一单一个"),
    ("gmv", "商品金额", "不含运费"),
    ("freight", "运费", "占销售额约 16.6%"),
    ("order_amount", "订单总金额", "商品金额 + 运费"),
    ("n_payments", "支付笔数", "一单可分多次支付"),
    ("payment_total", "支付总额", "与 order_amount 基本相等"),
    ("max_installments", "最大分期数", "巴西分期文化"),
    ("main_payment_type", "主支付方式", "金额最大的那种"),
    ("review_score", "评分", "1–5，多评价取最新一条"),
    ("n_reviews", "评价条数", ">1 说明用户改过评价"),
    ("no_review / is_low_score / is_high_score", "无评价 / 差评 / 好评", "差评=≤2 星，好评=≥4 星"),
    ("order_month / order_ym", "下单月份", "月度趋势用 order_ym"),
    ("order_dow / order_hour", "星期几 / 小时", "下单时段规律"),
    ("is_weekend", "是否周末", "1/0"),
    ("customer_order_seq", "该客户第几单", "1=首单"),
    ("customer_total_orders", "该客户累计下单数", ">1 即复购客户"),
    ("is_first_order", "是否首单", "1/0"),
]


def main() -> None:
    con = duckdb.connect()
    sql = SQL_FILE.read_text(encoding="utf-8")

    print("执行 SQL 建宽表 …")
    df = con.execute(sql).df()
    print(f"宽表行数：{len(df):,}   列数：{len(df.columns)}\n")

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)

    # ---------- 体检一：粒度是否被放大 ----------
    print("【体检 1】粒度")
    n_orders = con.execute(
        "SELECT COUNT(DISTINCT order_id) FROM read_csv_auto('data/raw/olist_orders_dataset.csv')"
    ).fetchone()[0]
    print(f"  原始订单数 {n_orders:,}  宽表行数 {len(df):,}", end="  ")
    print("√ 一单一行" if len(df) == n_orders else "× 行数被放大了，检查 join")

    # ---------- 体检二：金额勾稽 ----------
    print("\n【体检 2】金额勾稽")
    diff = (df["order_amount"] - df["gmv"].fillna(0) - df["freight"].fillna(0)).abs()
    print(f"  order_amount = gmv + freight 的最大偏差：{diff.max():.6f}")
    gap = (df["payment_total"] - df["order_amount"]).abs()
    print(f"  支付总额 vs 订单金额：{gap.median():.2f}（中位差），"
          f"其中 |差|>0.01 的占 {(gap > 0.01).mean():.2%}")

    # ---------- 体检三：分维度字段是否有效 ----------
    print("\n【体检 3】分维度字段")
    print(f"  客户数（去重人）      : {df.customer_unique_id.nunique():,}")
    print(f"  州数                  : {df.customer_state.nunique()}")
    print(f"  主品类数              : {df.main_category.nunique()}")
    print(f"  主品类缺失            : {df.main_category.isna().sum():,}")
    print(f"  支付方式              : {df.main_payment_type.dropna().unique().tolist()}")

    # ---------- 体检四：核心指标是否和摸底一致 ----------
    print("\n【体检 4】核心指标复核（应与摸底一致）")
    d = df[df.is_delivered == 1]
    print(f"  已送达订单           : {len(d):,}（{len(d)/len(df):.2%}）")
    print(f"  延迟率               : {d.is_late.mean():.2%}   ← 摸底 8.11%")
    print(f"  平均评分             : {df.review_score.mean():.2f}   ← 摸底 4.09")
    print(f"  差评率（≤2星）       : {df.is_low_score.mean():.2%}   ← 摸底 14.69%")
    rep = (df.drop_duplicates("customer_unique_id").customer_total_orders > 1).mean()
    print(f"  复购率               : {rep:.2%}   ← 摸底 3.12%")

    # ---------- 延迟效应的初步对照（分层前） ----------
    print("\n【预告】未做混杂控制时的延迟效应")
    dd = d.dropna(subset=["is_late", "review_score"])
    late = dd[dd.is_late == 1].review_score.mean()
    ok = dd[dd.is_late == 0].review_score.mean()
    print(f"  延迟订单均分 {late:.2f}  准时订单均分 {ok:.2f}  原始差 {ok-late:.2f}")
    print("  ↑ 这个差值是第 2 周的核心任务：拆开看有多少是地区/品类造成的")

    # ---------- 写字段说明 ----------
    lines = ["# 宽表字段说明\n", f"共 {len(df):,} 行 × {len(df.columns)} 列\n",
             "| 字段 | 中文 | 说明 |", "|---|---|---|"]
    for col, cn, note in DICT:
        lines.append(f"| `{col}` | {cn} | {note} |")
    OUT_DICT.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n宽表已写入 {OUT_PARQUET}")
    print(f"字段说明已写入 {OUT_DICT}")


if __name__ == "__main__":
    main()
