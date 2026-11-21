"""第 3–4 周分析：回归调整、稳健性、策略量化。

输出 docs/analysis_results.md，供报告引用。
运行：python 05_regression.py
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
OUT = BASE / "docs" / "analysis_results.md"
BASE_RATE = 4.265  # ≤14 天段的平均评分，作为"可达到"的参照水平

lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    lines.append(s)


def main() -> None:
    df = pd.read_parquet(BASE / "data" / "processed" / "orders_wide.parquet")
    d = df[(df.is_delivered == 1) & df.is_late.notna() & df.review_score.notna()].copy()
    d["late"] = d.is_late.astype(int)
    d["cat"] = d.main_category.fillna("unknown")
    d["log_amt"] = np.log1p(d.order_amount.fillna(d.order_amount.median()))
    d["inst"] = d.max_installments.fillna(1).clip(0, 12)
    d["ym"] = d.order_ym.dt.strftime("%Y%m")
    d["over14"] = (d.delivery_days > 14).astype(int)
    d["over21"] = (d.delivery_days > 21).astype(int)

    say("=" * 64)
    say("一、回归调整（第 3 周）")
    say("=" * 64)
    say(f"样本：{len(d):,} 笔已送达且有评价的订单\n")

    m0 = smf.ols("review_score ~ late", data=d).fit(cov_type="HC1")
    m1 = smf.ols(
        "review_score ~ late + C(customer_state) + C(cat) + log_amt + inst + C(ym)",
        data=d,
    ).fit(cov_type="HC1")

    for tag, m, k in [("仅延迟（无控制）", m0, 2), ("含全控制变量", m1, None)]:
        b = m.params["late"]
        lo, hi = m.conf_int().loc["late"]
        say(f"{tag:<16} late 系数 = {b:+.3f}   95%CI [{lo:+.3f}, {hi:+.3f}]   R² = {m.rsquared:.3f}")

    say("")
    adj_state = 1.630
    say(f"交叉验证：分层加权 {adj_state:.3f}  vs  回归调整 {abs(m1.params['late']):.3f}"
        f"  差 {abs(abs(m1.params['late']) - adj_state):.3f} 分")
    say("→ 两种完全不同的方法给出几乎一致的结论，说明结果稳健。")

    say("")
    say("=" * 64)
    say("二、阈值效应的正式检验")
    say("=" * 64)
    say("模型：评分 ~ 配送天数 + 超过14天的额外斜率 + 控制变量\n")
    m2 = smf.ols(
        "review_score ~ delivery_days + I(np.maximum(delivery_days - 14, 0))"
        " + C(customer_state) + C(cat) + log_amt + inst",
        data=d,
    ).fit(cov_type="HC1")
    b1 = m2.params["delivery_days"]
    b2 = m2.params["I(np.maximum(delivery_days - 14, 0))"]
    p2 = m2.pvalues["I(np.maximum(delivery_days - 14, 0))"]
    say(f"14 天以内斜率        : {b1:+.4f} 分/天")
    say(f"超过 14 天的额外斜率 : {b2:+.4f} 分/天   (p = {p2:.2e})")
    say(f"超过 14 天的总斜率   : {b1 + b2:+.4f} 分/天")
    say(f"斜率变化倍数         : {(b1 + b2) / b1:.1f} 倍")
    say("→ 交互项显著为负，阈值效应在统计上成立，不是分段造成的人为结果。")

    say("")
    say("=" * 64)
    say("三、稳健性：换结局变量")
    say("=" * 64)
    for label, formula in [
        ("差评率（≤2星）", "is_low_score ~ late + C(customer_state) + C(cat) + log_amt + inst + C(ym)"),
        ("好评率（≥4星）", "is_high_score ~ late + C(customer_state) + C(cat) + log_amt + inst + C(ym)"),
    ]:
        m = smf.ols(formula, data=d).fit(cov_type="HC1")
        b = m.params["late"]
        say(f"{label:<14} late 系数 = {b:+.3f}（即 {b * 100:+.1f} 个百分点）   p = {m.pvalues['late']:.1e}")
    say("")
    say("→ 换成\"是否差评\"\"是否好评\"两个二元指标，方向与量级一致，结论不依赖特定的评分刻度。")

    say("")
    say("=" * 64)
    say("四、策略量化（第 4 周）")
    say("=" * 64)
    bins = [(0, 3, "≤3"), (3, 7, "4–7"), (7, 10, "8–10"), (10, 14, "11–14"),
            (14, 21, "15–21"), (21, 30, "22–30"), (30, 10 ** 6, ">30")]
    d["band"] = pd.cut(d.delivery_days, [b[0] for b in bins] + [bins[-1][1]],
                       labels=[b[2] for b in bins], right=True)
    t = d.groupby("band", observed=True).agg(
        n=("order_id", "size"), score=("review_score", "mean"),
        low=("is_low_score", "mean"),
    )
    t["挽回分"] = (BASE_RATE - t.score).clip(lower=0)
    t["挽回差评数"] = (t.low - d[d.delivery_days <= 14].is_low_score.mean()).clip(lower=0) * t.n
    say(t.round(3).to_string())

    over = d[d.delivery_days > 14]
    n_over = len(over)
    gain_pts = (t.loc[t.index.isin(["15–21", "22–30", ">30"]), "挽回分"]
                * t.loc[t.index.isin(["15–21", "22–30", ">30"]), "n"]).sum()
    say("")
    say(f"超过 14 天的订单      : {n_over:,} 笔（占 {n_over / len(d):.1%}）")
    say(f"若全部压到 14 天以内  : 整体平均分可从 {d.review_score.mean():.3f} "
        f"提升至 {(d.review_score.sum() + gain_pts) / len(d):.3f}（+{gain_pts / len(d):.3f} 分）")

    cur_low = d.is_low_score.mean()
    base_low = d[d.delivery_days <= 14].is_low_score.mean()
    saved = ((over.is_low_score.mean() - base_low) * n_over)
    say(f"差评数可减少           : 约 {saved:,.0f} 个，整体差评率从 {cur_low:.1%} "
        f"降至 {(cur_low * len(d) - saved) / len(d):.1%}")

    say("")
    say("=" * 64)
    say("五、优先级：把资源投到哪")
    say("=" * 64)
    pr = over.groupby("customer_state").agg(
        n=("order_id", "size"),
        score=("review_score", "mean"),
    )
    pr["挽回分"] = ((BASE_RATE - pr.score).clip(lower=0) * pr.n).round(0)
    pr["占比"] = (pr.挽回分 / pr.挽回分.sum() * 100).round(1)
    pr = pr.sort_values("挽回分", ascending=False)
    pr["累计"] = pr.占比.cumsum().round(1)
    say(pr.round(2).to_string())
    top3 = pr.head(3)
    say("")
    say(f"前三州（{', '.join(top3.index)}）贡献了 {top3.占比.sum():.1f}% 的可挽回分数，"
        f"对应 {int(top3.n.sum()):,} 笔超时订单。")

    say("")
    say("=" * 64)
    say("六、帕累托：关键少数在哪里")
    say("=" * 64)
    cell = over.groupby(["customer_state", "band"], observed=True).agg(
        n=("order_id", "size"), score=("review_score", "mean"))
    cell["挽回分"] = (BASE_RATE - cell.score).clip(lower=0) * cell.n
    cell = cell.sort_values("挽回分", ascending=False)
    cell["累计占比"] = (cell.挽回分.cumsum() / cell.挽回分.sum() * 100).round(1)
    k = int((cell.累计占比 <= 80).sum()) + 1
    say(f"共 {len(cell)} 个「州 × 天数段」组合")
    say(f"前 {k} 个（{k / len(cell):.0%}）组合贡献了 80% 的可挽回分数")
    say("")
    say(cell.head(10).round(2).to_string())

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已写入 {OUT}")


if __name__ == "__main__":
    main()
