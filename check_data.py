"""检查 Olist 数据是否下载完整、字段是否正确。

用法：
    python check_data.py

把 9 个 csv 放进 data/raw/ 后运行。全部 OK 再开始做分析。
"""

import sys
from pathlib import Path

import pandas as pd

# Windows 控制台默认 GBK，中文会乱码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW = Path(__file__).parent / "data" / "raw"

# 实际记录数（用 pandas 解析后的条数，不是物理行数）
EXPECTED = {
    "olist_customers_dataset.csv": 99441,
    "olist_geolocation_dataset.csv": 1000163,
    "olist_order_items_dataset.csv": 112650,
    "olist_order_payments_dataset.csv": 103886,
    "olist_order_reviews_dataset.csv": 99224,
    "olist_orders_dataset.csv": 99441,
    "olist_products_dataset.csv": 32951,
    "olist_sellers_dataset.csv": 3095,
    "product_category_name_translation.csv": 71,
}


def main() -> None:
    if not RAW.exists():
        print(f"[×] 找不到目录：{RAW}")
        return

    found = {p.name for p in RAW.glob("*.csv")}
    missing = sorted(set(EXPECTED) - found)
    extra = sorted(found - set(EXPECTED))

    print(f"目录：{RAW}\n")

    ok = 0
    for name, expect in EXPECTED.items():
        path = RAW / name
        if not path.exists():
            print(f"[×] {name:<42} 缺失")
            continue
        try:
            df = pd.read_csv(path, nrows=5)
            # 注意：不能用数物理行数的方式统计，评论字段内含换行符，
            # 会让物理行数大于真实记录数（reviews 差 5495 行）
            total = len(pd.read_csv(path, usecols=[0]))
        except Exception as exc:  # 编码/分隔符错误在这里暴露
            print(f"[×] {name:<42} 读取失败：{exc}")
            continue

        flag = "[√]" if abs(total - expect) < 5 else "[!]"
        if flag == "[√]":
            ok += 1
        print(f"{flag} {name:<42} 行数 {total:>8,}  列数 {len(df.columns):>3}")
        print(f"    字段：{', '.join(df.columns)}")

    print()
    if extra:
        print(f"多余文件（不影响，但通常用不到）：{extra}")
    if missing:
        print(f"缺失文件：{missing}")
    print(f"校验结果：{ok}/{len(EXPECTED)} 个文件行数符合预期")

    # 关键提醒：客户表有两列编号，做留存/复购必须用 customer_unique_id
    cust = RAW / "olist_customers_dataset.csv"
    if cust.exists():
        c = pd.read_csv(cust)
        print(
            f"\n客户表：customer_id 唯一值 {c['customer_id'].nunique():,}，"
            f"customer_unique_id 唯一值 {c['customer_unique_id'].nunique():,}"
        )
        print("→ 两者数量不同。做复购/留存请用 customer_unique_id，"
              "用 customer_id 会得出复购率为 0。")


if __name__ == "__main__":
    main()
