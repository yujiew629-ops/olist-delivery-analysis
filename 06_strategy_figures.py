"""第 4 周：策略量化与图 9、图 10。

运行：python 06_strategy_figures.py
产出：report/figures/fig9_pareto.png、fig10_strategy.png、docs/strategy.md
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.25
plt.rcParams["grid.linestyle"] = "--"

BASE = Path(__file__).parent
FIG = BASE / "report" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
BASE_RATE = 4.265          # ≤14 天段平均评分
BASE_LOW = 0.090           # ≤14 天段平均差评率
C_BLUE, C_RED, C_GRAY, C_GREEN = "#2E5E8C", "#C0504D", "#9A9A9A", "#4F7F3F"

lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    lines.append(s)


def main() -> None:
    df = pd.read_parquet(BASE / "data" / "processed" / "orders_wide.parquet")
    d = df[(df.is_delivered == 1) & df.review_score.notna()].copy()

    bands = [(0, 3, "≤3"), (3, 7, "4–7"), (7, 10, "8–10"), (10, 14, "11–14"),
             (14, 21, "15–21"), (21, 30, "22–30"), (30, 10 ** 6, ">30")]
    d["band"] = pd.cut(d.delivery_days, [b[0] for b in bands] + [bands[-1][1]],
                       labels=[b[2] for b in bands], right=True)

    # ---------- 帕累托 ----------
    over = d[d.delivery_days > 14]
    cell = over.groupby(["customer_state", "band"], observed=True).agg(
        n=("order_id", "size"), score=("review_score", "mean"))
    cell["挽回分"] = (BASE_RATE - cell.score).clip(lower=0) * cell.n
    cell = cell.sort_values("挽回分", ascending=False).reset_index()
    cell["累计占比"] = cell.挽回分.cumsum() / cell.挽回分.sum() * 100
    k80 = int((cell.累计占比 < 80).sum()) + 1

    fig, ax1 = plt.subplots(figsize=(11, 5.8))
    xpos = np.arange(len(cell))
    ax1.bar(xpos, cell.挽回分.values, color=C_BLUE, alpha=0.75, width=0.8)
    ax1.set_xlabel("「州 × 天数段」组合（按可挽回分数降序）", fontsize=11)
    ax1.set_ylabel("可挽回分数（分·单）", color=C_BLUE, fontsize=11)
    ax1.tick_params(axis="y", labelcolor=C_BLUE)
    ax1.set_xticks([])

    ax2 = ax1.twinx()
    ax2.plot(xpos, cell.累计占比.values, color=C_RED, lw=2.2)
    ax2.axhline(80, color=C_GRAY, ls="--", lw=1.4)
    ax2.text(len(cell) * 0.62, 82, "80% 分位线", fontsize=9, color=C_GRAY)
    ax2.set_ylabel("累计占比（%）", color=C_RED, fontsize=11)
    ax2.tick_params(axis="y", labelcolor=C_RED)
    ax2.set_ylim(0, 105)
    ax2.grid(False)

    ax1.axvline(k80 - 0.5, color=C_GREEN, ls=":", lw=1.8)
    ax1.set_title(
        f"帕累托：前 {k80} 个组合（占全部 {len(cell)} 个的 {k80 / len(cell):.0%}）"
        f"贡献了 80% 的可挽回分数",
        fontsize=13, pad=14,
    )
    fig.tight_layout()
    fig.savefig(FIG / "fig9_pareto.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [完成] fig9_pareto.png")

    # ---------- 策略量化 ----------
    n_s1 = int((d.band == "15–21").sum())
    n_s2 = int(d.band.isin(["22–30", ">30"]).sum())
    low_s1 = d[d.band == "15–21"].is_low_score.mean()
    low_s2 = d[d.band.isin(["22–30", ">30"])].is_low_score.mean()

    cut1 = (low_s1 - BASE_LOW) * n_s1          # 压回 14 天：完全达到基线
    cut2 = (low_s2 - BASE_LOW) * n_s2 * 0.5    # 超 21 天：补偿只能挽回一半
    tgt1 = BASE_LOW                            # 全部压回 14 天，差评率降到基线
    tgt2 = low_s2 - (low_s2 - BASE_LOW) * 0.5  # 只能挽回一半缺口
    n_all = len(d)
    cur_low = d.is_low_score.mean()

    t = pd.DataFrame([
        {"策略": "A 守住 14 天", "对象": "15–21 天订单", "覆盖订单": n_s1,
         "当前差评率": low_s1, "目标差评率": tgt1, "减少差评": round(cut1, 0)},
        {"策略": "B 超 21 天主动补偿", "对象": "22 天以上订单", "覆盖订单": n_s2,
         "当前差评率": low_s2, "目标差评率": tgt2,
         "减少差评": round(cut2, 0)},
    ])
    say("## 策略量化\n")
    say(t.to_markdown(index=False))
    say("")
    say(f"合计可减少差评 **{cut1 + cut2:,.0f}** 个，"
        f"整体差评率从 {cur_low:.1%} 降至 {(cur_low * n_all - cut1 - cut2) / n_all:.1%}。")
    say("")
    say(f"注：策略 B 假设补偿沟通只能挽回一半的潜在差评，属于保守估计。")

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    xs = np.arange(2)
    w = 0.34
    ax.bar(xs - w / 2, t.当前差评率 * 100, w, label="实施前差评率", color=C_RED, alpha=0.85)
    ax.bar(xs + w / 2, t.目标差评率 * 100, w, label="实施后差评率", color=C_GREEN, alpha=0.85)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{a}\n覆盖 {b:,} 单\n可减 {c:,.0f} 个差评"
                        for a, b, c in zip(t.策略, t.覆盖订单, t.减少差评)], fontsize=9.5)
    ax.set_ylabel("差评率（%）", fontsize=11)
    ax.set_ylim(0, max(t.当前差评率) * 130)
    ax.legend(fontsize=10)
    for i, (c, g) in enumerate(zip(t.当前差评率, t.目标差评率)):
        ax.text(i - w / 2, c * 100 + 0.6, f"{c * 100:.1f}%", ha="center", fontsize=9)
        ax.text(i + w / 2, g * 100 + 0.6, f"{g * 100:.1f}%", ha="center", fontsize=9)
    ax.set_title(
        f"两条策略合计减少约 {cut1 + cut2:,.0f} 个差评，整体差评率 "
        f"{cur_low:.1%} → {(cur_low * n_all - cut1 - cut2) / n_all:.1%}",
        fontsize=12.5, pad=14,
    )
    fig.tight_layout()
    fig.savefig(FIG / "fig10_strategy.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [完成] fig10_strategy.png")

    # 州优先级表
    pr = over.groupby("customer_state").agg(n=("order_id", "size"), score=("review_score", "mean"))
    pr["挽回分"] = ((BASE_RATE - pr.score).clip(lower=0) * pr.n).round(0)
    pr = pr.sort_values("挽回分", ascending=False).head(8)
    pr["占全部可挽回分"] = (pr.挽回分 / (BASE_RATE - over.review_score).clip(lower=0).mul(0).sum()
                       if False else pr.挽回分 / cell.挽回分.sum() * 100).round(1)
    say("\n## 州优先级（前 8）\n")
    say(pr.round(2).to_markdown())

    (BASE / "docs" / "strategy.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n已写入 docs/strategy.md")


if __name__ == "__main__":
    main()
