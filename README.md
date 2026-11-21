# 配送延迟如何影响用户满意度

基于 Olist 巴西电商平台 99,441 笔订单的因果分析项目。

**核心问题**：配送延迟对用户评分的真实伤害有多大？其中有多少是地区差异造成的假象？

---

## 核心发现

| # | 结论 | 证据 |
|---|---|---|
| 1 | 延迟订单评分低 **1.73 分**，控制地区后仍为 **1.63 分**（仅降 5.6%） | 分层加权 + 回归调整，两种方法交叉验证 |
| 2 | 配送天数与评分是**阈值关系**：14 天内每天降 0.020 分，15 天起每天降 0.078 分（**3.9 倍**） | 7 段分箱 + 阈值交互项回归（p < 0.001） |
| 3 | 问题高度集中：28.7% 的超时订单贡献绝大部分差评，**前 25% 的组合占 80%** 可挽回分数 | 帕累托分析（81 个「州 × 天数段」组合） |
| 4 | 两条策略合计可减少约 **2,285 个差评**，差评率 12.8% → 10.4% | 分箱基线 + 保守挽回率假设 |

---

## 项目结构

```
olist-growth-analysis/
├── README.md
├── requirements.txt
├── PROGRESS.md                 项目执行记录（4 周迭代过程）
│
├── check_data.py               数据完整性校验
├── 01_data_profile.py          数据摸底，产出字段字典
├── 02_build_wide_table.py      宽表构建（DuckDB，41 字段）
├── 03_load_to_mysql.py         宽表导入 MySQL
├── 04_make_figures.py          图 1–8
├── 05_regression.py            回归调整、阈值检验、稳健性
├── 06_strategy_figures.py      图 9–10、策略量化
│
├── sql/
│   ├── 01_build_wide_table.sql         宽表 DDL（DuckDB 版）
│   ├── 01b_build_wide_table_mysql.sql  宽表 DDL（MySQL 版，可直接执行）
│   ├── 02_state.sql                    按州分析
│   ├── 03_stratified.sql               分层加权
│   └── 04_dose_response.sql            剂量反应分箱
│
├── report/
│   ├── 完整报告.md              主报告（含 10 张图）
│   ├── 01_现状结论.md
│   ├── 02_混杂诊断.md
│   └── figures/                 fig1–fig10
│
└── docs/
    ├── data_profile.txt        数据摸底结果
    ├── wide_table_dict.md      宽表字段说明
    ├── analysis_results.md     回归与策略量化输出
    └── strategy.md             策略明细
```

---

## 如何复现

### 1. 环境

```bash
pip install -r requirements.txt
```

### 2. 下载数据

从 Kaggle 下载 [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，将 9 个 CSV 放入 `data/raw/`。

### 3. 依次执行

```bash
python check_data.py            # 校验数据完整性
python 01_data_profile.py       # 数据摸底
python 02_build_wide_table.py   # 构建宽表 → data/processed/orders_wide.parquet
python 04_make_figures.py       # 生成图 1–8
python 05_regression.py         # 回归与稳健性 → docs/analysis_results.md
python 06_strategy_figures.py   # 图 9–10 与策略量化
```

可选：导入 MySQL 后在 DataGrip 中用 SQL 探索

```bash
python 03_load_to_mysql.py      # 需要本地 MySQL
```

---

## 技术栈

- **数据处理**：Python（pandas / numpy）、DuckDB、PyArrow
- **SQL**：MySQL 8.0（窗口函数、CTE、条件聚合）
- **统计建模**：statsmodels（OLS、固定效应、异方差稳健标准误）
- **可视化**：matplotlib
- **工具**：DataGrip

---

## 方法要点

1. **粒度纪律**：宽表严格保持「一行 = 一个订单」，明细表先聚合再关联，避免行数膨胀与金额重复累加。
2. **稳健性交叉验证**：分层加权（非参数）与多元回归（参数化）两条独立路径，结论一致才下判断。
3. **诚实报告不确定性**：拐点在统计上 10–16 天不可区分，14 天是业务选择；评价缺失非随机，估计存在低估。

---

## 数据来源

Olist 公开数据集，覆盖 2016 年 9 月至 2018 年 10 月，99,441 笔订单。数据仅用于分析练习。
