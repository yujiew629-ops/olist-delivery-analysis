"""生成报告用的 6 张图。

运行：
    python 04_make_figures.py

产出（都写进 report/figures/）：
    fig1_monthly.png         月度订单量与延迟率
    fig2_march_daily.png     2018年3月的断点
    fig3_state_delay.png     各州延迟率排序
    fig4_state_scatter.png   州：延迟率 vs 平均评分
    fig5_category.png        品类：延迟率 vs 评分落差
    fig6_score_dist.png      延迟vs准时 的评分分布

为什么从 parquet 读而不连 MySQL：
    图表脚本不需要密码就能重复运行，别人拿到项目也能一键复现。
    SQL 分析在 DataGrip 里做，这里的职责只是"把已有结论画出来"。
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
FIG_DIR = BASE / "report" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

W_START, W_END = "2017-02", "2018-08"   # 分析窗口：月延迟单 >= 30 的月份
C_BLUE = "#2E5E8C"
C_RED = "#C0504D"
C_GRAY = "#9A9A9A"
C_GREEN = "#4F7F3F"


def load() -> pd.DataFrame:
    df = pd.read_parquet(BASE / "data" / "processed" / "orders_wide.parquet")
    df["ym"] = df["order_ym"].dt.strftime("%Y-%m")
    return df


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [完成] {name}")


def in_window(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df.ym >= W_START) & (df.ym <= W_END)]


# ---------------------------------------------------------------- 图 1
def fig1_monthly(df: pd.DataFrame) -> None:
    d = in_window(df)
    vol = d.groupby("ym").size()
    rate = d[d.is_delivered == 1].groupby("ym")["is_late"].mean() * 100

    months = vol.index.tolist()
    x = np.arange(len(months))

    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax1.bar(x, vol.values, color=C_BLUE, alpha=0.75, width=0.65, label="订单量")
    ax1.set_ylabel("订单量（单）", color=C_BLUE, fontsize=11)
    ax1.tick_params(axis="y", labelcolor=C_BLUE)

    ax2 = ax1.twinx()
    ax2.plot(x, rate.values, color=C_RED, marker="o", lw=2.2, label="延迟率")
    ax2.set_ylabel("延迟率（%）", color=C_RED, fontsize=11)
    ax2.tick_params(axis="y", labelcolor=C_RED)
    ax2.grid(False)

    peak = int(np.argmax(vol.values))
    ax1.annotate(
        f"大促：{vol.values[peak]:,} 单\n延迟率 {rate.values[peak]:.1f}%",
        xy=(x[peak], vol.values[peak]),
        xytext=(x[peak] - 4.2, vol.values[peak] * 0.92),
        fontsize=9,
        color=C_RED,
        arrowprops=dict(arrowstyle="->", color=C_RED, lw=1.2),
    )

    ax1.set_xticks(x)
    ax1.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
    pv, pr = vol.idxmax(), rate.idxmax()
    ax1.set_title(
        f"订单量在 {pv} 大促见顶（{vol.max():,} 单），延迟率峰值出现在 {pr}（{rate.max():.1f}%）",
        fontsize=13,
        pad=14,
    )
    save(fig, "fig1_monthly.png")


# ---------------------------------------------------------------- 图 2
def fig2_march_daily(df: pd.DataFrame) -> None:
    m = df[(df.purchase_ts >= "2018-03-01") & (df.purchase_ts < "2018-04-01")].copy()
    m["d"] = m.purchase_ts.dt.day
    rate = m[m.is_delivered == 1].groupby("d")["is_late"].mean() * 100
    score = m.groupby("d")["review_score"].mean()

    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax1.plot(rate.index, rate.values, color=C_RED, marker="o", ms=4, lw=2, label="延迟率")
    ax1.set_xlabel("2018 年 3 月（日）", fontsize=11)
    ax1.set_ylabel("延迟率（%）", color=C_RED, fontsize=11)
    ax1.tick_params(axis="y", labelcolor=C_RED)
    ax1.set_xticks(range(1, 32))
    ax1.set_xticklabels(range(1, 32), fontsize=8)

    ax2 = ax1.twinx()
    ax2.plot(score.index, score.values, color=C_BLUE, marker="s", ms=3.5, lw=1.8,
             alpha=0.85, label="平均评分")
    ax2.set_ylabel("平均评分", color=C_BLUE, fontsize=11)
    ax2.tick_params(axis="y", labelcolor=C_BLUE)
    ax2.set_ylim(3.2, 4.3)
    ax2.grid(False)

    ax1.axvline(17.5, color=C_GRAY, ls="--", lw=1.6)
    ax1.text(17.9, rate.max() * 0.95, "3月18日\n结构性断点", fontsize=10, color=C_GRAY)

    b, a = rate.loc[1:17], rate.loc[18:31]
    ax1.set_title(
        f"2018年3月18日起延迟率中枢下移：前17天均值 {b.mean():.1f}%，"
        f"后14天均值 {a.mean():.1f}%",
        fontsize=13,
        pad=14,
    )
    save(fig, "fig2_march_daily.png")


# ---------------------------------------------------------------- 图 3
def fig3_state_delay(df: pd.DataFrame) -> None:
    d = df[df.is_delivered == 1].dropna(subset=["is_late", "review_score"])
    g = d.groupby("customer_state")
    t = pd.DataFrame({
        "n": g.size(),
        "late_rate": g["is_late"].mean() * 100,
        "score": g["review_score"].mean(),
    })
    t = t[t.n >= 300].sort_values("late_rate")

    fig, ax = plt.subplots(figsize=(10, 7))
    colors = [C_RED if r >= 12 else C_BLUE for r in t.late_rate]
    ax.barh(t.index, t.late_rate.values, color=colors, alpha=0.85)
    ax.set_xlabel("延迟率（%）", fontsize=11)
    ax.set_title(
        f"各州延迟率最大相差 {t.late_rate.max() / t.late_rate.min():.1f} 倍："
        "东北部各州普遍偏高，南部与东南部最低",
        fontsize=13, pad=14,
    )

    for i, (state, row) in enumerate(t.iterrows()):
        ax.text(row.late_rate + 0.25, i, f"{row.late_rate:.1f}%  (评分{row.score:.2f})",
                va="center", fontsize=8, color="#333333")
    ax.set_xlim(0, t.late_rate.max() * 1.35)
    save(fig, "fig3_state_delay.png")


# ---------------------------------------------------------------- 图 4
def fig4_state_scatter(df: pd.DataFrame) -> None:
    d = df[df.is_delivered == 1].dropna(subset=["is_late", "review_score"])
    g = d.groupby("customer_state")
    t = pd.DataFrame({
        "n": g.size(),
        "late_rate": g["is_late"].mean() * 100,
        "score": g["review_score"].mean(),
    })
    t = t[t.n >= 300]

    fig, ax = plt.subplots(figsize=(10, 6.5))
    ax.scatter(t.late_rate, t.score, s=t.n / 12, alpha=0.55, color=C_BLUE,
               edgecolors="white", linewidths=1.2)
    for state, row in t.iterrows():
        ax.annotate(state, (row.late_rate, row.score), fontsize=9,
                    xytext=(4, 4), textcoords="offset points", color="#333333")

    z = np.polyfit(t.late_rate, t.score, 1)
    xs = np.linspace(t.late_rate.min(), t.late_rate.max(), 50)
    r = np.corrcoef(t.late_rate, t.score)[0, 1]
    ax.plot(xs, np.polyval(z, xs), color=C_RED, ls="--", lw=1.6,
            label=f"趋势线（r = {r:.2f}）")
    ax.legend(fontsize=10, loc="lower left")

    ax.set_xlabel("延迟率（%）", fontsize=11)
    ax.set_ylabel("平均评分", fontsize=11)
    ax.set_title(
        f"州维度上延迟率与平均评分负相关（r = {r:.2f}，R² = {r ** 2:.2f}），气泡大小代表订单量",
        fontsize=13, pad=14,
    )
    save(fig, "fig4_state_scatter.png")


# ---------------------------------------------------------------- 图 5
def fig5_category(df: pd.DataFrame) -> None:
    d = df[(df.is_delivered == 1) & df.main_category.notna()
           & (df.main_category != "unknown")].dropna(subset=["is_late", "review_score"])
    g = d.groupby("main_category")
    t = pd.DataFrame({"n": g.size()})
    t["late_rate"] = g["is_late"].mean() * 100
    t["ontime"] = d[d.is_late == 0].groupby("main_category")["review_score"].mean()
    t["late"] = d[d.is_late == 1].groupby("main_category")["review_score"].mean()
    t["gap"] = t.ontime - t.late
    t = t[(t.n >= 300) & (d.groupby("main_category")["is_late"].sum() >= 30)]

    fig, ax = plt.subplots(figsize=(11, 6.8))
    sc = ax.scatter(t.gap, t.late_rate, s=t.n / 6, alpha=0.6, c=t.ontime,
                    cmap="RdYlGn", edgecolors="white", linewidths=1.2)
    cb = plt.colorbar(sc, ax=ax)
    cb.set_label("准时均分", fontsize=10)

    # 标签太多会糊成一团：只标落差两端 + 订单量最大的几个
    by_gap = t.sort_values("gap")
    label_set = list(by_gap.head(4).index) + list(by_gap.tail(4).index)
    label_set += [x for x in t.sort_values("n", ascending=False).index[:2]
                  if x not in label_set]
    for name in label_set:
        row = t.loc[name]
        ax.annotate(name, (row.gap, row.late_rate), fontsize=8,
                    xytext=(6, 5), textcoords="offset points", color="#222222")

    ax.margins(x=0.12, y=0.10)
    ax.set_xlabel("评分落差（准时均分 − 延迟均分）", fontsize=11)
    ax.set_ylabel("延迟率（%）", fontsize=11)
    ax.set_title(
        f"品类间延迟率跨度 {t.late_rate.min():.1f}%–{t.late_rate.max():.1f}%，"
        f"评分落差跨度 {t.gap.min():.2f}–{t.gap.max():.2f}",
        fontsize=13, pad=14,
    )
    save(fig, "fig5_category.png")


# ---------------------------------------------------------------- 图 6
def fig6_score_dist(df: pd.DataFrame) -> None:
    d = df[df.is_delivered == 1].dropna(subset=["is_late", "review_score"])
    on = d[d.is_late == 0].review_score.value_counts(normalize=True).sort_index() * 100
    late = d[d.is_late == 1].review_score.value_counts(normalize=True).sort_index() * 100

    idx = [1, 2, 3, 4, 5]
    x = np.arange(len(idx))
    w = 0.38

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(x - w / 2, [on.get(i, 0) for i in idx], w, label="准时订单", color=C_BLUE, alpha=0.85)
    ax.bar(x + w / 2, [late.get(i, 0) for i in idx], w, label="延迟订单", color=C_RED, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{i} 星" for i in idx], fontsize=11)
    ax.set_ylabel("占比（%）", fontsize=11)
    ax.legend(fontsize=10)
    ax.set_title(
        f"延迟订单的 1 星占比从 {on.get(1, 0):.1f}% 升至 {late.get(1, 0):.1f}%，"
        f"5 星从 {on.get(5, 0):.1f}% 降至 {late.get(5, 0):.1f}%",
        fontsize=13, pad=14,
    )

    for i, v in enumerate([on.get(j, 0) for j in idx]):
        ax.text(i - w / 2, v + 1, f"{v:.1f}", ha="center", fontsize=8)
    for i, v in enumerate([late.get(j, 0) for j in idx]):
        ax.text(i + w / 2, v + 1, f"{v:.1f}", ha="center", fontsize=8)

    save(fig, "fig6_score_dist.png")


def fig7_stratified(df: pd.DataFrame) -> None:
    """图 7：各州评分落差 + 加权前后对比。"""
    d = df[df.is_delivered == 1].dropna(subset=["is_late", "review_score"])
    g = d.groupby("customer_state")
    t = pd.DataFrame({
        "n": g.size(),
        "n_late": g["is_late"].sum(),
        "late_avg": d[d.is_late == 1].groupby("customer_state").review_score.mean(),
        "on_avg": d[d.is_late == 0].groupby("customer_state").review_score.mean(),
    })
    t["gap"] = t.on_avg - t.late_avg
    t = t.dropna()
    # 与 sql/03_stratified.sql 的口径一致：总单 >=300 且延迟单 >=30
    ok = t[(t.n >= 300) & (t.n_late >= 30)].sort_values("gap")

    crude = d[d.is_late == 0].review_score.mean() - d[d.is_late == 1].review_score.mean()
    adj = (ok.gap * ok.n).sum() / ok.n.sum()

    fig, ax = plt.subplots(figsize=(9.5, 7.6))
    ypos = np.arange(len(ok))
    norm = (ok.n - ok.n.min()) / (ok.n.max() - ok.n.min())
    colors = plt.cm.Blues(0.35 + 0.55 * norm.values)

    ax.hlines(ypos, 0, ok.gap.values, color="#CCCCCC", lw=1.2, zorder=1)
    ax.scatter(ok.gap.values, ypos, s=30 + 260 * norm.values,
               color=colors, edgecolors="white", linewidths=1.2, zorder=4)

    ax.axvline(crude, color=C_RED, ls="--", lw=1.6, zorder=2)
    ax.axvline(adj, color=C_GREEN, ls="-", lw=2.0, zorder=2)
    ax.text(crude + 0.03, len(ok) - 0.4, f"粗效应 {crude:.2f}", color=C_RED,
            fontsize=10, va="top")
    ax.text(adj - 0.03, len(ok) - 0.4, f"加权后 {adj:.2f}", color=C_GREEN,
            fontsize=10, va="top", ha="right")

    ax.set_yticks(ypos)
    ax.set_yticklabels(ok.index)
    for i, (state, row) in enumerate(ok.iterrows()):
        ax.text(row.gap + 0.04, i, f"{row.gap:.2f}  (n={int(row.n):,})",
                va="center", fontsize=7.5, color="#444444")

    ax.set_xlim(0, ok.gap.max() * 1.32)
    ax.set_ylim(-1.0, len(ok) - 0.2)
    ax.set_xlabel("州内评分落差（准时均分 − 延迟均分）", fontsize=11)
    ax.set_title(
        f"{len(ok)} 个州的落差从 {ok.gap.min():.2f} 到 {ok.gap.max():.2f}，"
        f"按订单量加权后由 {crude:.2f} 降至 {adj:.2f}（仅降 {(1 - adj / crude) * 100:.1f}%）",
        fontsize=12.5, pad=14,
    )
    save(fig, "fig7_stratified.png")


def fig8_dose_response(df: pd.DataFrame) -> None:
    """图 8：配送天数与评分的剂量反应，重点展示 15 天后的加速。"""
    d = df[(df.is_delivered == 1) & df.review_score.notna()].copy()
    labels = ["≤3", "4–7", "8–10", "11–14", "15–21", "22–30", ">30"]
    d["level"] = pd.cut(d.delivery_days, [0, 3, 7, 10, 14, 21, 30, 10_000],
                        labels=labels)
    t = d.groupby("level", observed=True).agg(
        n=("order_id", "size"),
        days=("delivery_days", "mean"),
        score=("review_score", "mean"),
    )

    x, y = t.days.values, t.score.values
    z1 = np.polyfit(x[:4], y[:4], 1)      # 前四段：≤14 天
    z2 = np.polyfit(x[4:], y[4:], 1)      # 后三段：>14 天

    fig, ax = plt.subplots(figsize=(10.8, 6.4))

    # 数据点（大小正比于样本量），不连折线，避免盖住拟合线
    ax.scatter(x, y, s=t.n.values / 45, color=C_BLUE, alpha=0.75,
               edgecolors="white", linewidths=1.5, zorder=5, label="分段平均评分")

    xs1 = np.linspace(x[0], x[3], 30)
    xs2 = np.linspace(x[3], x[-1], 30)
    ax.plot(xs1, np.polyval(z1, xs1), color=C_GREEN, ls="-", lw=3.0,
            alpha=0.9, zorder=3,
            label=f"≤14 天拟合：每多 1 天 {z1[0]:.3f} 分")
    ax.plot(xs2, np.polyval(z2, xs2), color=C_RED, ls="-", lw=3.0,
            alpha=0.9, zorder=3,
            label=f">14 天拟合：每多 1 天 {z2[0]:.3f} 分")

    # 二次拟合只作参照：形状接近，但没有拐点，且外推会跌破 1 分下限
    q = np.polyfit(x, y, 2)
    xq = np.linspace(0, 60, 200)
    ax.plot(xq, np.polyval(q, xq), color="#888888", ls=":", lw=1.6, zorder=2,
            label="二次拟合（R²=0.997，但无拐点、60 天外推为负）")

    for xi, yi, ni, lb in zip(x, y, t.n.values, labels):
        ax.annotate(f"{lb}天\nn={ni:,}", (xi, yi), fontsize=7.5,
                    xytext=(0, 16), textcoords="offset points",
                    ha="center", color="#555555")

    ax.axvline(14.5, color=C_GRAY, ls=":", lw=1.6, zorder=1)
    ax.text(15.3, 4.52, "15 天：斜率跳变 3.9 倍", fontsize=9.5, color="#666666")

    ax.set_xlabel("平均配送天数", fontsize=11)
    ax.set_ylabel("平均评分", fontsize=11)
    ax.set_ylim(1.9, 4.75)
    ax.set_xlim(x[0] - 3, x[-1] + 4)
    ax.legend(fontsize=9.5, loc="lower left")
    ax.set_title(
        f"剂量反应存在阈值：14 天内每多一天约降 {abs(z1[0]):.3f} 分，"
        f"15 天后约降 {abs(z2[0]):.3f} 分（{abs(z2[0] / z1[0]):.1f} 倍）",
        fontsize=13, pad=14,
    )
    save(fig, "fig8_dose_response.png")


def main() -> None:
    if not (BASE / "data" / "processed" / "orders_wide.parquet").exists():
        print("找不到宽表，先跑 02_build_wide_table.py")
        return

    df = load()
    print("生成图表：")
    fig1_monthly(df)
    fig2_march_daily(df)
    fig3_state_delay(df)
    fig4_state_scatter(df)
    fig5_category(df)
    fig6_score_dist(df)
    fig7_stratified(df)
    fig8_dose_response(df)
    print(f"\n全部写入 {FIG_DIR}")


if __name__ == "__main__":
    main()
