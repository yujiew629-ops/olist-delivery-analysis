"""把 report/完整报告.md 转成排版好的 DOCX（含封面、目录、页码）。

运行：
    python build_docx.py
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
MD = BASE / "report" / "完整报告.md"
OUT = BASE / "report" / "完整报告.docx"

FONT_CN = "微软雅黑"
FONT_BODY = "宋体"
TITLE = "配送延迟如何影响用户满意度"
SUBTITLE = "—— 基于 Olist 电商平台 9.9 万笔订单的因果分析"


def set_font(run, name=FONT_BODY, size=None, bold=None, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_inline(par, text, size=10.5, base_bold=False):
    tokens = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for tk in tokens:
        if not tk:
            continue
        if tk.startswith("**") and tk.endswith("**"):
            r = par.add_run(tk[2:-2])
            set_font(r, FONT_BODY, size, bold=True)
        elif tk.startswith("`") and tk.endswith("`"):
            r = par.add_run(tk[1:-1])
            set_font(r, "Consolas", size - 0.5, color=(0x2E, 0x5E, 0x8C))
        else:
            r = par.add_run(tk)
            set_font(r, FONT_BODY, size, bold=base_bold)


def shade(cell, hexcolor):
    el = OxmlElement("w:shd")
    el.set(qn("w:fill"), hexcolor)
    cell._tc.get_or_add_tcPr().append(el)


def add_table(doc, rows):
    header, body = rows[0], rows[1:]
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h.strip())
        set_font(r, FONT_CN, 9, bold=True)
        shade(c, "E8EEF4")
    for row in body:
        cells = t.add_row().cells
        for i, v in enumerate(row[: len(header)]):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i else WD_ALIGN_PARAGRAPH.LEFT
            add_inline(p, v.strip(), 9)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_code(doc, lines):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.1
    r = p.add_run("\n".join(lines))
    r.font.name = "Consolas"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def add_image(doc, alt, path):
    full = (MD.parent / path).resolve()
    if not full.exists():
        print(f"  [缺图] {full}")
        return
    doc.add_picture(str(full), width=Cm(15.2))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.paragraphs[-1].paragraph_format.space_before = Pt(6)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(alt)
    set_font(r, FONT_CN, 8.5, color=(0x66, 0x66, 0x66))
    cap.paragraph_format.space_after = Pt(12)


def add_page_numbers(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    f1 = OxmlElement("w:fldChar")
    f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = "PAGE"
    f2 = OxmlElement("w:fldChar")
    f2.set(qn("w:fldCharType"), "end")
    run._r.append(f1)
    run._r.append(it)
    run._r.append(f2)
    set_font(run, FONT_CN, 9, color=(0x99, 0x99, 0x99))


def hr(doc, color="CCCCCC"):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), color)
    pbdr.append(bottom)
    pPr.append(pbdr)
    p.paragraph_format.space_after = Pt(2)


def add_code_appendix(doc, files):
    """附录 C：分析 SQL。"""
    from docx.enum.text import WD_BREAK as BRK

    doc.add_paragraph().add_run().add_break(BRK.PAGE)
    p = doc.add_paragraph()
    r = p.add_run("附录 C：分析 SQL")
    set_font(r, FONT_CN, 14, bold=True, color=(0x1F, 0x3B, 0x5C))
    p.paragraph_format.space_after = Pt(6)
    hr(doc, "B8C7D9")

    p = doc.add_paragraph()
    r = p.add_run("下列 SQL 按执行顺序覆盖报告的完整分析链，运行环境为 MySQL 8.0，"
                  "数据表为 wide_orders_native。各段独立可执行。")
    set_font(r, FONT_BODY, 9.5, color=(0x55, 0x55, 0x55))
    p.paragraph_format.space_after = Pt(12)

    for label, rel in files:
        path = BASE / rel
        if not path.exists():
            continue
        code = path.read_text(encoding="utf-8").rstrip()

        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(label)
        set_font(r, FONT_CN, 10.5, bold=True, color=(0x1F, 0x3B, 0x5C))
        r2 = p.add_run(f"　{rel}　({len(code.splitlines())} 行)")
        set_font(r2, "Consolas", 8, color=(0x88, 0x88, 0x88))

        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Cm(0.2)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(code)
        run.font.name = "Consolas"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
        run.font.size = Pt(7.2)
        run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)


def main() -> None:
    text = MD.read_text(encoding="utf-8")
    blocks = [b.strip("\n") for b in re.split(r"\n\s*\n", text) if b.strip()]

    h2s = []
    for b in blocks:
        s = b.strip()
        if s.startswith("## ") and "\n" not in s and not s.startswith("### "):
            t = s[3:].strip()
            if not t.startswith("——"):
                h2s.append(t)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.6)
    sec.top_margin = sec.bottom_margin = Cm(2.4)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_BODY
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_BODY)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)

    add_page_numbers(sec)

    # ---------------- 封面 ----------------
    for _ in range(2):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(TITLE)
    set_font(r, FONT_CN, 26, bold=True, color=(0x14, 0x2B, 0x45))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    r = p.add_run(SUBTITLE)
    set_font(r, FONT_CN, 13, color=(0x55, 0x55, 0x55))

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(28)
    hr(doc)

    for label, value in [
        ("数据来源", "Olist Brazilian E-Commerce Public Dataset"),
        ("样本规模", "99,441 笔订单 · 96,096 位客户 · 27 个州"),
        ("方法", "分层加权 · 固定效应回归 · 阈值检验 · 帕累托分析"),
        ("工具", "Python（pandas / statsmodels）· DuckDB · MySQL · matplotlib"),
        ("日期", "2026 年 11 月"),
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(label + "　")
        set_font(r, FONT_CN, 9, bold=True, color=(0x66, 0x66, 0x66))
        r = p.add_run(value)
        set_font(r, FONT_CN, 9, color=(0x44, 0x44, 0x44))

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------------- 目录 ----------------
    p = doc.add_paragraph()
    r = p.add_run("目　录")
    set_font(r, FONT_CN, 16, bold=True, color=(0x1F, 0x3B, 0x5C))
    p.paragraph_format.space_after = Pt(14)
    hr(doc)
    for i, t in enumerate(h2s, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.left_indent = Cm(0.3)
        r = p.add_run(t)
        set_font(r, FONT_CN, 10.5, color=(0x33, 0x33, 0x33))
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------------- 正文 ----------------
    for block in blocks:
        s = block.strip()
        if s == "---":
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", s, re.S)
        if m and "\n" not in s:
            level, txt = len(m.group(1)), m.group(2).strip()
            if level == 1:
                continue          # 封面已处理
            if txt.startswith("——"):
                continue          # 副标题已处理
            p = doc.add_paragraph()
            r = p.add_run(txt)
            sizes = {2: 14, 3: 12}
            set_font(r, FONT_CN, sizes[level], bold=True, color=(0x1F, 0x3B, 0x5C))
            p.paragraph_format.space_before = Pt(18 if level == 2 else 12)
            p.paragraph_format.space_after = Pt(8)
            if level == 2:
                hr(doc, "B8C7D9")
            continue

        m = re.match(r"^!\[(.*?)\]\((.*?)\)$", s)
        if m:
            add_image(doc, m.group(1), m.group(2))
            continue

        if s.startswith("|"):
            rows = []
            for ln in s.split("\n"):
                ln = ln.strip()
                if not ln.startswith("|") or re.match(r"^\|[\s:\-\|]+\|$", ln):
                    continue
                rows.append(ln.strip("|").split("|"))
            if rows:
                add_table(doc, rows)
            continue

        if s.startswith("```"):
            body = [ln for ln in s.split("\n")[1:] if not ln.startswith("```")]
            add_code(doc, body)
            continue

        if s.startswith(">"):
            lines = [ln.lstrip("> ").strip() for ln in s.split("\n")]
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(8)
            add_inline(p, " ".join(x for x in lines if x), 10)
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            continue

        if re.match(r"^(\d+\.|[-*])\s+", s):
            for ln in s.split("\n"):
                mm = re.match(r"^(\d+\.|[-*])\s+(.*)$", ln.strip())
                if not mm:
                    continue
                marker = "• " if mm.group(1) in "-*" else mm.group(1) + " "
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.7)
                p.paragraph_format.first_line_indent = Cm(-0.45)
                p.paragraph_format.space_after = Pt(3)
                add_inline(p, marker + mm.group(2), 10.5)
            continue

        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0)
        add_inline(p, " ".join(x.strip() for x in s.split("\n")), 10.5)

    add_code_appendix(doc, [
        ("完整分析 SQL（0–10 段）", "sql/00_全流程.sql"),
    ])

    doc.save(OUT)
    print(f"已生成 {OUT}")

    d2 = Document(OUT)
    print(f"段落 {len(d2.paragraphs)}  表格 {len(d2.tables)}  图片 {len(d2.inline_shapes)}")

if __name__ == "__main__":
    main()
