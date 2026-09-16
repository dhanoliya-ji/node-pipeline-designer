"""Renders `PROBLEM_STATEMENT.md` to a typeset PDF.

A small Markdown renderer rather than a dependency on pandoc, so the PDF can
be rebuilt anywhere the backend's dev requirements are installed:

    backend/.venv/Scripts/python docs/build_pdf.py

It supports the subset the document actually uses — headings, paragraphs,
bullet and numbered lists, pipe tables, block quotes, horizontal rules, and
inline bold/italic/code — and deliberately nothing more. Anything it does not
recognise is emitted as plain text rather than silently dropped.
"""

import re
import sys
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / 'PROBLEM_STATEMENT.md'
TARGET = DOCS / 'PROBLEM_STATEMENT.pdf'

# Matches the palette the app itself uses, so the document and the product
# look like they belong to each other.
INK = colors.HexColor('#16192b')
INK_SOFT = colors.HexColor('#5b6178')
INK_MUTED = colors.HexColor('#8a90a6')
BRAND = colors.HexColor('#5a4bff')
RULE = colors.HexColor('#e2e6f0')
SHADE = colors.HexColor('#f4f6fb')
CODE_BG = colors.HexColor('#eef1f8')


# --------------------------------------------------------------------------
# Styles
# --------------------------------------------------------------------------

def build_styles():
    base = getSampleStyleSheet()
    fonts = {'body': 'Helvetica', 'bold': 'Helvetica-Bold', 'mono': 'Courier'}

    styles = {
        'title': ParagraphStyle(
            'title', parent=base['Title'], fontName=fonts['bold'],
            fontSize=26, leading=31, textColor=INK, spaceAfter=4,
            alignment=TA_LEFT),
        'subtitle': ParagraphStyle(
            'subtitle', fontName=fonts['body'], fontSize=13.5, leading=18,
            textColor=INK_SOFT, spaceAfter=18),
        'byline': ParagraphStyle(
            'byline', fontName=fonts['body'], fontSize=9.5, leading=13,
            textColor=INK_MUTED, spaceAfter=6),
        'h1': ParagraphStyle(
            'h1', fontName=fonts['bold'], fontSize=16, leading=21,
            textColor=INK, spaceBefore=20, spaceAfter=8),
        'h2': ParagraphStyle(
            'h2', fontName=fonts['bold'], fontSize=12.5, leading=17,
            textColor=INK, spaceBefore=15, spaceAfter=6),
        'h3': ParagraphStyle(
            'h3', fontName=fonts['bold'], fontSize=10.5, leading=15,
            textColor=INK_SOFT, spaceBefore=12, spaceAfter=4),
        'body': ParagraphStyle(
            'body', fontName=fonts['body'], fontSize=9.7, leading=14.6,
            textColor=INK, spaceAfter=8),
        'quote': ParagraphStyle(
            'quote', fontName=fonts['bold'], fontSize=10.5, leading=16,
            textColor=BRAND, leftIndent=14, spaceBefore=6, spaceAfter=10,
            borderPadding=(0, 0, 0, 8)),
        'item': ParagraphStyle(
            'item', fontName=fonts['body'], fontSize=9.7, leading=14.2,
            textColor=INK, spaceAfter=3),
        'cell': ParagraphStyle(
            'cell', fontName=fonts['body'], fontSize=8.3, leading=11.6,
            textColor=INK),
        'cellhead': ParagraphStyle(
            'cellhead', fontName=fonts['bold'], fontSize=8.3, leading=11.6,
            textColor=INK),
        'footer': ParagraphStyle(
            'footer', fontName=fonts['body'], fontSize=7.8, leading=10,
            textColor=INK_MUTED),
    }
    styles['fonts'] = fonts
    return styles


# --------------------------------------------------------------------------
# Inline markup
# --------------------------------------------------------------------------

def inline(text: str) -> str:
    """Converts inline Markdown to ReportLab's mini-HTML.

    Escaping happens first so that a literal `<` in the source cannot become
    a tag, and the code spans are styled last so their contents are left
    alone.
    """
    text = (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    text = re.sub(r'`([^`]+)`',
                  r'<font face="Courier" size="8.6" backColor="#eef1f8">\1</font>',
                  text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    # Single asterisks, but not the ones that were half of a bold pair.
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  r'<link href="\2" color="#5a4bff">\1</link>', text)

    # Typographic details the document relies on.
    text = text.replace('--', '&#8212;').replace('->', '&#8594;')
    return text


# --------------------------------------------------------------------------
# Block parsing
# --------------------------------------------------------------------------

def split_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def is_divider(line: str) -> bool:
    """A table's `|---|:--:|` separator row."""
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r':?-{2,}:?', c) for c in cells)


def build_table(rows: List[List[str]], styles, width: float) -> Table:
    header, *body = rows
    columns = len(header)

    data = [[Paragraph(inline(cell), styles['cellhead']) for cell in header]]
    for row in body:
        # A malformed row is padded rather than raising, so one bad line in
        # the source cannot fail the whole build.
        padded = (row + [''] * columns)[:columns]
        data.append([Paragraph(inline(cell), styles['cell']) for cell in padded])

    # The first column usually holds a short key (an id, a number); giving it
    # less room keeps the prose columns readable.
    if columns >= 3:
        first = width * 0.13
        rest = (width - first) / (columns - 1)
        col_widths = [first] + [rest] * (columns - 1)
    else:
        col_widths = [width / columns] * columns

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SHADE),
        ('LINEBELOW', (0, 0), (-1, 0), 0.9, RULE),
        ('LINEBELOW', (0, 1), (-1, -2), 0.4, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def parse(markdown: str, styles, width: float) -> List:
    lines = markdown.split('\n')
    flow: List = []
    index = 0
    seen_title = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        # Horizontal rule.
        if re.fullmatch(r'-{3,}|\*{3,}|_{3,}', stripped):
            flow.append(Spacer(1, 4))
            flow.append(HRFlowable(width='100%', thickness=0.7, color=RULE,
                                   spaceBefore=2, spaceAfter=10))
            index += 1
            continue

        # Table: a pipe row followed by a divider row.
        if (stripped.startswith('|') and index + 1 < len(lines)
                and is_divider(lines[index + 1])):
            rows = [split_row(stripped)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith('|'):
                rows.append(split_row(lines[index]))
                index += 1
            flow.append(Spacer(1, 3))
            flow.append(build_table(rows, styles, width))
            flow.append(Spacer(1, 11))
            continue

        # Headings.
        heading = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if heading:
            level, text = len(heading.group(1)), heading.group(2)
            if level == 1 and not seen_title:
                seen_title = True
                flow.append(Paragraph(inline(text), styles['title']))
            elif level == 2 and not any(
                    isinstance(f, Paragraph) and f.style.name == 'h1'
                    for f in flow):
                # The document's one subtitle: the h2 before any h1.
                flow.append(Paragraph(inline(text), styles['subtitle']))
            else:
                style = styles['h1'] if level <= 2 else (
                    styles['h2'] if level == 3 else styles['h3'])
                flow.append(Paragraph(inline(text), style))
            index += 1
            continue

        # Block quote.
        if stripped.startswith('>'):
            quoted = []
            while index < len(lines) and lines[index].strip().startswith('>'):
                quoted.append(lines[index].strip().lstrip('>').strip())
                index += 1
            flow.append(Paragraph(inline(' '.join(quoted)), styles['quote']))
            continue

        # Bullet or numbered list.
        bullet = re.match(r'^[-*+]\s+(.*)$', stripped)
        number = re.match(r'^\d+[.)]\s+(.*)$', stripped)
        if bullet or number:
            ordered = bool(number)
            items = []
            while index < len(lines):
                current = lines[index].strip()
                match = (re.match(r'^\d+[.)]\s+(.*)$', current) if ordered
                         else re.match(r'^[-*+]\s+(.*)$', current))
                if not match:
                    # A wrapped continuation line belongs to the item above.
                    if current and not re.match(r'^(#{1,6}\s|\||>|-{3,})', current) \
                            and items and lines[index].startswith(('  ', '\t')):
                        items[-1] += ' ' + current
                        index += 1
                        continue
                    break
                items.append(match.group(1))
                index += 1

            # `value` sets a numbered item's number and is meaningless for a
            # bullet, where ReportLab would try to draw the integer as the
            # bullet glyph.
            def make_item(index_, text_):
                extra = {'value': index_ + 1} if ordered else {}
                return ListItem(Paragraph(inline(text_), styles['item']),
                                leftIndent=16, **extra)

            flow.append(ListFlowable(
                [make_item(i, item) for i, item in enumerate(items)],
                bulletType='1' if ordered else 'bullet',
                bulletFontSize=8, bulletColor=BRAND,
                leftIndent=16, spaceBefore=2, spaceAfter=9,
            ))
            continue

        # Paragraph: consume until a blank line or the start of another block.
        paragraph = []
        while index < len(lines):
            current = lines[index].strip()
            if not current or re.match(r'^(#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>|-{3,}$)',
                                       current):
                break
            paragraph.append(current)
            index += 1
        if paragraph:
            flow.append(Paragraph(inline(' '.join(paragraph)), styles['body']))

    return flow


# --------------------------------------------------------------------------
# Page furniture
# --------------------------------------------------------------------------

def decorate(canvas, doc):
    """Draws the running footer: title on the left, page number on the right."""
    canvas.saveState()
    width, _ = A4

    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(20 * mm, 16 * mm, width - 20 * mm, 16 * mm)

    canvas.setFont('Helvetica', 7.8)
    canvas.setFillColor(INK_MUTED)
    canvas.drawString(20 * mm, 11.5 * mm,
                      'Node Pipeline Designer  ·  Problem statement and objectives')
    canvas.drawRightString(width - 20 * mm, 11.5 * mm, str(doc.page))

    canvas.restoreState()


def build() -> Path:
    if not SOURCE.exists():
        raise SystemExit('missing source: {}'.format(SOURCE))

    styles = build_styles()
    doc = BaseDocTemplate(
        str(TARGET),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=22 * mm,
        title='Node Pipeline Designer — Problem statement and objectives',
        author='dhanoliya-ji',
        subject='Problem statement, objectives, approach and evaluation',
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id='body', leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame],
                                       onPage=decorate)])

    flow = parse(SOURCE.read_text(encoding='utf-8'), styles, doc.width)
    doc.build(flow)
    return TARGET


if __name__ == '__main__':
    written = build()
    print('wrote {} ({:,} bytes)'.format(written, written.stat().st_size))
