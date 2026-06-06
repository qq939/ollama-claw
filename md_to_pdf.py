#!/usr/bin/env python3
"""Render the openclaw-gateway-pairing notes into a PDF using reportlab."""

import re
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Preformatted,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

# Register CJK fonts. reportlab ships with built-in CID fonts that handle
# CJK characters without needing a local TTF file. STSong-Light is for
# Simplified Chinese.
CJK_BODY = "STSong-Light"
CJK_BOLD = "STSong-Light"  # STSong has no bold variant; reuse for headings
CJK_MONO = "STSong-Light"  # Code blocks render Chinese characters fine with this
# Pre-register before building styles so ParagraphStyle can reference them.
pdfmetrics.registerFont(UnicodeCIDFont(CJK_BODY))

SRC = Path(r"C:\Users\qq939\Downloads\ollama-claw\openclaw-gateway-pairing-notes.md")
OUT = Path(r"C:\Users\qq939\Downloads\ollama-claw\openclaw-gateway-pairing-notes.pdf")


def make_styles():
    styles = getSampleStyleSheet()
    # Body
    styles.add(ParagraphStyle(
        name="BodyCJK",
        parent=styles["BodyText"],
        fontName=CJK_BODY,
        fontSize=10.5,
        leading=15,
        spaceAfter=6,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="H1CJK",
        parent=styles["Heading1"],
        fontName=CJK_BOLD,
        fontSize=18,
        leading=24,
        spaceBefore=4,
        spaceAfter=10,
        textColor=HexColor("#0F172A"),
    ))
    styles.add(ParagraphStyle(
        name="H2CJK",
        parent=styles["Heading2"],
        fontName=CJK_BOLD,
        fontSize=14,
        leading=20,
        spaceBefore=10,
        spaceAfter=6,
        textColor=HexColor("#0F172A"),
    ))
    styles.add(ParagraphStyle(
        name="H3CJK",
        parent=styles["Heading3"],
        fontName=CJK_BOLD,
        fontSize=11.5,
        leading=17,
        spaceBefore=8,
        spaceAfter=4,
        textColor=HexColor("#1E3A8A"),
    ))
    styles.add(ParagraphStyle(
        name="QuoteCJK",
        parent=styles["BodyText"],
        fontName=CJK_BODY,
        fontSize=10,
        leading=14,
        leftIndent=14,
        rightIndent=8,
        spaceBefore=4,
        spaceAfter=6,
        textColor=HexColor("#1F2937"),
        backColor=HexColor("#F3F4F6"),
        borderPadding=6,
    ))
    styles.add(ParagraphStyle(
        name="CodeCJK",
        parent=styles["Code"],
        fontName=CJK_MONO,
        fontSize=9,
        leading=12,
        leftIndent=8,
        rightIndent=8,
        spaceBefore=2,
        spaceAfter=6,
        backColor=HexColor("#0F172A"),
        textColor=HexColor("#E5E7EB"),
        borderPadding=6,
    ))
    styles.add(ParagraphStyle(
        name="BulletCJK",
        parent=styles["BodyText"],
        fontName=CJK_BODY,
        fontSize=10.5,
        leading=15,
        leftIndent=18,
        bulletIndent=6,
        spaceAfter=2,
    ))
    return styles


def render_inline(text: str) -> str:
    """Convert markdown-ish inline syntax to reportlab Paragraph markup."""
    # Escape XML special chars first
    out = (text
           .replace("&", "&amp;")
           .replace("<", "&lt;")
           .replace(">", "&gt;"))
    # Bold **xxx**
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    # Italic *xxx* or _xxx_
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", out)
    # Inline code `xxx`
    out = re.sub(
        r"`([^`]+?)`",
        rf'<font name="{CJK_MONO}" color="#0F172A" backColor="#F3F4F6">\1</font>',
        out,
    )
    return out


def flush_paragraph(buf, styles, story):
    if not buf.strip():
        return
    text = render_inline(buf.strip())
    story.append(Paragraph(text, styles["BodyCJK"]))


def render_table_row(cells, is_header, styles):
    """Render a markdown table row into a list of Paragraphs."""
    out = []
    for c in cells:
        style = styles["H3CJK"] if is_header else styles["BodyCJK"]
        out.append(Paragraph(render_inline(c.strip().replace("\n", "<br/>")), style))
    return out


def parse_md(text: str, styles):
    lines = text.splitlines()
    story = []
    i = 0
    para_buf = []
    in_code = False
    code_lines = []
    code_lang = ""

    def flush():
        flush_paragraph("".join(para_buf), styles, story)
        para_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Code fence
        if stripped.startswith("```"):
            if in_code:
                # close code block
                code_text = "\n".join(code_lines)
                try:
                    pf = Preformatted(code_text, styles["CodeCJK"])
                    story.append(pf)
                except Exception:
                    story.append(Paragraph(render_inline(code_text.replace("<", "&lt;")), styles["CodeCJK"]))
                code_lines = []
                in_code = False
            else:
                flush()
                in_code = True
                code_lang = stripped[3:].strip()
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Headings
        if stripped.startswith("# "):
            flush()
            story.append(Paragraph(render_inline(stripped[2:]), styles["H1CJK"]))
        elif stripped.startswith("## "):
            flush()
            story.append(Paragraph(render_inline(stripped[3:]), styles["H2CJK"]))
        elif stripped.startswith("### "):
            flush()
            story.append(Paragraph(render_inline(stripped[4:]), styles["H3CJK"]))
        elif stripped.startswith("> "):
            flush()
            quote_text = stripped[2:].strip()
            story.append(Paragraph(render_inline(quote_text), styles["QuoteCJK"]))
        elif stripped.startswith("- "):
            flush()
            txt = stripped[2:].strip()
            story.append(Paragraph("• " + render_inline(txt), styles["BulletCJK"]))
        elif stripped.startswith("|") and i + 1 < len(lines) and lines[i+1].startswith("|---"):
            # Table: header row + separator + body rows
            flush()
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2  # skip separator
            body_rows = []
            while i < len(lines) and lines[i].startswith("|"):
                row_cells = [c.strip() for c in lines[i].strip("|").split("|")]
                body_rows.append(row_cells)
                i += 1
            data = [render_table_row(header_cells, True, styles)]
            for r in body_rows:
                # pad to header length
                r = r + [""] * (len(header_cells) - len(r))
                data.append(render_table_row(r, False, styles))
            t = Table(data, colWidths=[(A4[0] - 4*cm) / len(header_cells)] * len(header_cells), repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E0E7FF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#1E3A8A")),
                ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTNAME", (0, 0), (-1, -1), CJK_BODY),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))
            continue
        elif stripped.startswith("---"):
            flush()
            # Horizontal rule
            story.append(Spacer(1, 6))
        elif stripped == "":
            flush()
        else:
            para_buf.append(stripped + " ")

        i += 1

    flush()
    return story


def main():
    md = SRC.read_text(encoding="utf-8")
    styles = make_styles()

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="OpenClaw Gateway 连接与审批 — 官方文档解读",
        author="Mavis",
    )

    story = []
    # Title block
    story.append(Paragraph("OpenClaw Gateway 连接与审批", styles["H1CJK"]))
    story.append(Paragraph("官方文档（docs.openclaw.ai）原文摘录与现场对照", styles["H3CJK"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "整理时间：2026-06-03 · 来源：docs.openclaw.ai（gateway/pairing、cli/devices、gateway/troubleshooting、gateway/configuration 四页）",
        styles["BodyCJK"]))
    story.append(Spacer(1, 8))

    story.extend(parse_md(md, styles))

    # Footer / page number via onPage
    def add_page_number(canvas, doc_):
        canvas.saveState()
        canvas.setFont(CJK_BODY, 8)
        canvas.setFillColor(HexColor("#94A3B8"))
        canvas.drawString(2 * cm, 1 * cm,
                          "OpenClaw Gateway 连接与审批 — 官方文档解读")
        canvas.drawRightString(A4[0] - 2 * cm, 1 * cm,
                               f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Wrote {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
