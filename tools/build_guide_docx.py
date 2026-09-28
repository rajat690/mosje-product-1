"""Convert HOSTING_GUIDE.md -> HOSTING_GUIDE.docx (python-docx). Other guides:
python tools/build_guide_docx.py UPLOAD_GUIDE.md   (writes UPLOAD_GUIDE.docx next to it). Handles the subset of Markdown used
in the guide: headings, paragraphs, **bold**, *italic*, `code`, links, numbered/bulleted lists (nested),
code blocks, tables, images, block quotes, check boxes and horizontal rules."""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "HOSTING_GUIDE.md")
DST = SRC.with_suffix(".docx")
BLUE = RGBColor(0x1F, 0x4E, 0x79)

doc = Document()
sec = doc.sections[0]
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin = sec.bottom_margin = Cm(1.8)
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(10.5)
for lvl, size in ((1, 20), (2, 15), (3, 12.5)):
    h = doc.styles[f"Heading {lvl}"]
    h.font.name = "Calibri"
    h.font.size = Pt(size)
    h.font.color.rgb = BLUE

TOKEN = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)]+\)|https?://[^\s)]+)")


def shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def add_runs(p, text, bold=False):
    text = text.replace("[ ]", "☐")
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`") and part.endswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
        elif part.startswith("[") and "](" in part:
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part).groups()
            r = p.add_run(label); r.font.color.rgb = BLUE; r.underline = True
        elif part.startswith("http"):
            r = p.add_run(part); r.font.color.rgb = BLUE; r.underline = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            r = p.add_run(part[1:-1]); r.italic = True
        else:
            r = p.add_run(part)
        if bold:
            r.bold = True


def list_par(text, numbered, level, number=None):
    style = "List Number" if numbered else "List Bullet"
    if level >= 1:
        style += " 2"
    p = doc.add_paragraph(style=style if not numbered else ("List Bullet 2" if level >= 1 else "Normal"))
    if numbered and level == 0:
        p.paragraph_format.left_indent = Cm(0.9)
        p.paragraph_format.first_line_indent = Cm(-0.6)
        r = p.add_run(f"{number}. "); r.bold = True
    p.paragraph_format.space_after = Pt(3)
    add_runs(p, text)
    return p


def table(rows):
    rows = [r for r in rows if not re.match(r"^\|?\s*:?-{2,}", r.replace("|", "").strip() and r) or "---" not in r]
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    n = len(cells[0])
    t = doc.add_table(rows=len(cells), cols=n)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(cells):
        for j in range(n):
            c = t.cell(i, j)
            c.text = ""
            p = c.paragraphs[0]
            add_runs(p, row[j] if j < len(row) else "", bold=(i == 0))
            for r in p.runs:
                r.font.size = Pt(9.5)
                if i == 0:
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            if i == 0:
                shade(c, "1F4E79")
    doc.add_paragraph()


lines = SRC.read_text(encoding="utf-8").splitlines()
i = 0
num_counter = 0
while i < len(lines):
    ln = lines[i]
    s = ln.strip()
    if s.startswith("```"):
        code = []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("```"):
            code.append(lines[i]); i += 1
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.6)
        r = p.add_run("\n".join(code)); r.font.name = "Consolas"; r.font.size = Pt(9)
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F2F2F2"); pPr.append(shd)
        i += 1
        continue
    if s.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            if not re.match(r"^\|[\s:|-]+\|$", lines[i].strip()):
                rows.append(lines[i])
            i += 1
        cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
        n = len(cells[0])
        t = doc.add_table(rows=len(cells), cols=n)
        t.style = "Table Grid"
        for ri, row in enumerate(cells):
            for j in range(n):
                c = t.cell(ri, j)
                p = c.paragraphs[0]
                add_runs(p, row[j] if j < len(row) else "", bold=(ri == 0))
                for r in p.runs:
                    r.font.size = Pt(9.5)
                    if ri == 0:
                        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                if ri == 0:
                    shade(c, "1F4E79")
        doc.add_paragraph()
        continue
    m = re.match(r"^!\[[^\]]*\]\(([^)]+)\)", s)
    if m:
        doc.add_picture(str(ROOT / m.group(1)), width=Cm(17))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap = doc.add_paragraph("Figure: hosting architecture (dashboard → API → Postgres on Render; synthetic data only)")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].italic = True; cap.runs[0].font.size = Pt(9)
        i += 1
        continue
    if s.startswith("#"):
        level = len(s) - len(s.lstrip("#"))
        doc.add_heading(s.lstrip("#").strip(), level=min(level, 3))
        num_counter = 0
        i += 1
        continue
    if s == "---":
        p = doc.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr"); b = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "999999")):
            b.set(qn(k), v)
        bdr.append(b); pPr.append(bdr)
        i += 1
        continue
    if s.startswith(">"):
        text = [s.lstrip("> ").strip()]
        i += 1
        while i < len(lines) and lines[i].strip().startswith(">"):
            text.append(lines[i].strip().lstrip("> ").strip()); i += 1
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.6)
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "FFF2CC"); pPr.append(shd)
        add_runs(p, " ".join(text))
        continue
    m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", ln)
    if m:
        indent = len(m.group(1))
        text = m.group(3)
        i += 1
        while i < len(lines) and lines[i].startswith(" " * (indent + 3)) and not re.match(r"^\s*(\*|\d+\.)\s", lines[i]):
            text += " " + lines[i].strip(); i += 1
        list_par(text, True, 1 if indent >= 2 else 0, int(m.group(2)))
        continue
    m = re.match(r"^(\s*)\*\s+(.*)$", ln)
    if m:
        indent = len(m.group(1))
        text = m.group(2)
        i += 1
        while i < len(lines) and lines[i].startswith(" " * (indent + 2)) and lines[i].strip() and \
                not re.match(r"^\s*(\*|\d+\.)\s", lines[i]):
            text += " " + lines[i].strip(); i += 1
        list_par(text, False, 1 if indent >= 2 else 0)
        continue
    if not s:
        i += 1
        continue
    text = s
    i += 1
    while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(\*|\d+\.|#|\||>|```|!\[)", lines[i]):
        text += " " + lines[i].strip(); i += 1
    p = doc.add_paragraph()
    add_runs(p, text)

doc.core_properties.title = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("# ")), SRC.stem)
doc.core_properties.author = "MoSJE Product 1 team"
doc.save(DST)
print("saved", DST)
