"""把 Olist 的 8 张原始表 + 1 张宽表装进本地 MySQL，供 DataGrip 连接。

运行（在项目目录下）：
    python 03_load_to_mysql.py

运行后会提示输入 MySQL 的 root 密码（输入时不显示，属正常）。

也可以先把密码放进环境变量，避免每次输入：
    set OLIST_MYSQL_PWD=你的密码
    python 03_load_to_mysql.py

装完的库名：olist
"""

import getpass
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
RAW = BASE / "data" / "raw"
PROCESSED = BASE / "data" / "processed"

DB_NAME = "olist"

# 需要装进去的表：(表名, 文件, 是否解析日期列)
RAW_TABLES = [
    ("orders",            "olist_orders_dataset.csv", True),
    ("customers",         "olist_customers_dataset.csv", False),
    ("order_items",       "olist_order_items_dataset.csv", False),
    ("order_payments",    "olist_order_payments_dataset.csv", False),
    ("order_reviews",     "olist_order_reviews_dataset.csv", False),
    ("products",          "olist_products_dataset.csv", False),
    ("sellers",           "olist_sellers_dataset.csv", False),
    ("category_trans",    "product_category_name_translation.csv", False),
    # geolocation 有 100 万行且本分析用不到（customers 表已含城市和州），跳过
]

# 装完后建索引：(表名, 索引名, 列)
INDEXES = [
    ("orders",         "idx_orders_customer",  "customer_id"),
    ("order_items",    "idx_items_order",      "order_id"),
    ("order_payments", "idx_pay_order",        "order_id"),
    ("order_reviews",  "idx_rev_order",        "order_id"),
    ("wide_orders",    "idx_w_order",          "order_id"),
    ("wide_orders",    "idx_w_customer",       "customer_unique_id"),
    ("wide_orders",    "idx_w_state",          "customer_state"),
    ("wide_orders",    "idx_w_month",          "order_ym"),
]


def get_password() -> str:
    pwd = os.environ.get("OLIST_MYSQL_PWD")
    if pwd:
        print("使用环境变量 OLIST_MYSQL_PWD 中的密码")
        return pwd
    return getpass.getpass("请输入 MySQL root 密码（输入时不可见）：")


def main() -> None:
    pwd = get_password()
    url = f"mysql+pymysql://root:{pwd}@127.0.0.1:3306/?charset=utf8mb4"

    print("\n连接 MySQL …")
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            ver = conn.execute(text("SELECT VERSION()")).scalar()
        print(f"连接成功，MySQL {ver}")
    except Exception as exc:
        print(f"\n连接失败：{exc}")
        print("\n可能原因：")
        print("  1. 密码错误 —— 重跑一次，注意大小写")
        print("  2. 服务未启动 —— 管理员 PowerShell 执行: net start MySQL80")
        print("  3. 端口不是 3306 —— 检查 my.ini")
        return

    # ---------- 建库 ----------
    print(f"\n创建数据库 {DB_NAME} …")
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        conn.commit()

    db_url = f"mysql+pymysql://root:{pwd}@127.0.0.1:3306/{DB_NAME}?charset=utf8mb4"
    db = create_engine(db_url, pool_pre_ping=True)

    # ---------- 装原始表 ----------
    print("\n装载原始表：")
    for table, fname, parse_dates in RAW_TABLES:
        path = RAW / fname
        if not path.exists():
            print(f"  [跳过] {table}：找不到 {fname}")
            continue
        df = pd.read_csv(path)
        if parse_dates:
            for col in df.columns:
                if col.endswith("_date") or col.endswith("_timestamp") or col == "order_approved_at":
                    df[col] = pd.to_datetime(df[col], errors="coerce")
        df.to_sql(table, db, if_exists="replace", index=False, chunksize=3000)
        print(f"  [完成] {table:<14} {len(df):>8,} 行  {len(df.columns):>2} 列")

    # ---------- 装宽表 ----------
    parquet = PROCESSED / "orders_wide.parquet"
    if parquet.exists():
        print("\n装载宽表：")
        wide = pd.read_parquet(parquet)
        wide.to_sql("wide_orders", db, if_exists="replace", index=False, chunksize=3000)
        print(f"  [完成] wide_orders    {len(wide):>8,} 行  {len(wide.columns):>2} 列")
    else:
        print(f"\n[跳过] 找不到 {parquet}，先跑 02_build_wide_table.py")

    # ---------- 建索引 ----------
    print("\n建索引：")
    with db.connect() as conn:
        for table, idx, cols in INDEXES:
            try:
                conn.execute(text(f"CREATE INDEX `{idx}` ON `{table}` (`{cols}`)"))
                conn.commit()
                print(f"  [完成] {table}.{cols}")
            except Exception as exc:
                if "Duplicate" in str(exc):
                    print(f"  [已存在] {table}.{cols}")
                else:
                    print(f"  [失败] {table}.{cols}：{str(exc)[:80]}")

    # ---------- 验收 ----------
    print("\n验收：")
    with db.connect() as conn:
        tables = conn.execute(text("SHOW TABLES")).fetchall()
        for (t,) in tables:
            n = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            print(f"  {t:<16} {n:>9,} 行")

    print("\n" + "=" * 56)
    print("装库完成。下一步在 DataGrip 里连接：")
    print("=" * 56)
    print("  1. DataGrip 左上角 + 号 → Data Source → MySQL")
    print("  2. Host: 127.0.0.1    Port: 3306")
    print("  3. User: root         Password: 你的密码")
    print(f"  4. Database: {DB_NAME}")
    print("  5. 首次连接会提示 Download missing driver files，点它")
    print("  6. Test Connection 显示绿色对勾 → OK")
    print("\n  连上后在左侧展开 olist → tables，双击 wide_orders 即可看数据。")
    print("  按 Ctrl+Enter 执行选中的 SQL，建议先跑：")
    print("    SELECT customer_state, is_late, AVG(review_score) AS avg_score, COUNT(*) AS n")
    print("    FROM wide_orders")
    print("    WHERE is_delivered = 1 AND is_late IS NOT NULL")
    print("    GROUP BY customer_state, is_late")
    print("    ORDER BY customer_state;")


if __name__ == "__main__":
    main()
