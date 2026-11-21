"""生成数据分析岗简历（单页 A4）。

运行：
    python build_resume.py
产出：
    docs/简历_数据分析.docx
"""

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
OUT = BASE / "docs" / "简历_数据分析.docx"

FONT = "微软雅黑"
DARK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x55, 0x55, 0x55)
LINE = RGBColor(0x88, 0x88, 0x88)


def set_font(run, size=9.5, bold=False, color=DARK, name=FONT):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color


def bottom_border(par, color="999999", sz="6"):
    pPr = par._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), sz)
    b.set(qn("w:space"), "2")
    b.set(qn("w:color"), color)
    pbdr.append(b)
    pPr.append(pbdr)


def section(doc, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(title)
    set_font(r, 10.5, bold=True, color=RGBColor(0x1F, 0x3B, 0x5C))
    bottom_border(p)


def row(doc, left, right, left_bold=True, size=9.6):
    """一行两栏：左边学校/公司，右边时间。"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(16.6), WD_TAB_ALIGNMENT.RIGHT)
    r = p.add_run(left)
    set_font(r, size, bold=left_bold)
    r = p.add_run("\t" + right)
    set_font(r, 9, color=GRAY)


def bullet(doc, text, size=9.6):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.45)
    p.paragraph_format.first_line_indent = Cm(-0.45)
    p.paragraph_format.space_after = Pt(1.8)
    p.paragraph_format.line_spacing = 1.26
    r = p.add_run("· ")
    set_font(r, size, color=GRAY)
    # 支持「关键词：正文」加粗
    if "：" in text and len(text.split("：")[0]) <= 14:
        head, tail = text.split("：", 1)
        r = p.add_run(head + "：")
        set_font(r, size, bold=True)
        r = p.add_run(tail)
        set_font(r, size)
    else:
        r = p.add_run(text)
        set_font(r, size)


def main() -> None:
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin = s.right_margin = Cm(1.9)
    s.top_margin = Cm(1.5)
    s.bottom_margin = Cm(1.5)

    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(9.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.paragraph_format.space_after = Pt(0)
    st.paragraph_format.line_spacing = 1.15

    # ---------------- 抬头 ----------------
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run("【姓名】")
    set_font(r, 20, bold=True)

    r = p.add_run("　　求职意向：数据分析师（互联网 / 策略分析 · 实验科学）")
    set_font(r, 9.5, color=GRAY)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("138-0000-0000　|　your@email.com　|　github.com/yujiew629-ops　|　重庆 · 可异地实习")
    set_font(r, 9.2, color=GRAY)
    bottom_border(p, "333333", "8")

    # ---------------- 教育背景 ----------------
    section(doc, "教育背景")
    row(doc, "重庆大学　应用统计（硕士，两年制）", "2026.09 – 2028.06")
    bullet(doc, "主修课程：回归分析、多元统计分析、时间序列分析、抽样调查、统计计算、机器学习")
    row(doc, "安徽大学　统计学（本科）", "2022.09 – 2026.06")
    bullet(doc, "GPA：【填】/4.0（专业前 【填】%）　核心课程：概率论、数理统计、随机过程、计量经济学")

    # ---------------- 项目经历 ----------------
    section(doc, "项目经历")
    row(doc, "电商配送延迟对用户满意度的影响分析　|　个人项目", "2026.10 – 2026.11")
    bullet(doc, "宽表构建：基于 Olist 9.9 万笔订单构建 41 字段订单宽表（MySQL + DuckDB），"
                "处理明细表一对多聚合、一人多单主键、多值字段取值三类粒度问题，"
                "将订单表从 112,650 行明细压回 99,441 行订单粒度")
    bullet(doc, "效应估计：用分层加权与固定效应回归双路径估计延迟对评分的影响。"
                "粗效应 1.73 分，按订单量对 21 个州加权后降至 1.63 分（仅降 5.6%）；"
                "回归控制州、品类、金额、分期、月份后估计 1.665 分（95%CI −1.703 ~ −1.627）")
    bullet(doc, "阈值识别：通过 7 段分箱与阈值交互项回归（线性样条）识别出 14 天拐点，"
                "之后日均掉分由 0.020 升至 0.078（交互项 −0.0233，p < 0.001），"
                "并检验拐点在 10–16 天区间统计上不可区分")
    bullet(doc, "策略输出：用帕累托分析定位出占 80% 损失的前 25%「州 × 天数段」组合，"
                "提出「守住 14 天」与「超 21 天主动补偿」两条策略，测算可减少 2,285 个差评，"
                "整体差评率 12.8% → 10.4%")

    # ---------------- 专业技能 ----------------
    section(doc, "专业技能")
    bullet(doc, "SQL：窗口函数、CTE、多表关联、条件聚合；熟悉 MySQL 8.0，"
                "理解索引失效场景与执行顺序（WHERE / GROUP BY / HAVING）")
    bullet(doc, "Python：pandas / numpy 数据清洗与聚合，statsmodels 回归建模，matplotlib 可视化")
    bullet(doc, "统计方法：假设检验、置信区间、分层加权、多元回归与固定效应、"
                "A/B 实验设计与样本量计算、协变量平衡检验")
    bullet(doc, "机器学习：逻辑回归、GBDT / XGBoost、特征工程与模型评估；了解深度学习基础（PyTorch）")
    bullet(doc, "工具：MySQL、DuckDB、DataGrip、Git；英语 CET-6（【填】分）")

    # ---------------- 其他 ----------------
    section(doc, "其他")
    bullet(doc, "项目仓库：github.com/yujiew629-ops/olist-delivery-analysis"
                "（含 23 页报告、10 张图、完整 SQL 与 Python 代码）")
    bullet(doc, "竞赛 / 证书：【如数学建模、统计建模大赛、CDA 等，无则删掉本行】")
    bullet(doc, "自我评价：统计科班出身，习惯先确认口径再下结论；"
                "对混杂与因果区分较敏感，写分析时会主动标注估计的局限")

    doc.save(OUT)
    print(f"已生成 {OUT}")

    d2 = Document(OUT)
    print(f"段落 {len(d2.paragraphs)}")


if __name__ == "__main__":
    main()



