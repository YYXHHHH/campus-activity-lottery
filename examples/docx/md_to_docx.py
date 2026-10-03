# -*- coding: utf-8 -*-
"""Render the Markdown documents under docs/ into Word (.docx).

用法：python examples/docx/md_to_docx.py
Output: a same-named .docx next to each Markdown file (README.md -> documentation-index.docx).

渲染特性：A4、中文字体、封面页、自动目录（打开时更新）、页眉文档名、
页脚“第 X 页 / 共 Y 页”、表格边框与跨页重复表头、代码块灰底。
"""
import os
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.join(PROJECT, 'docs')
CN = '宋体'
CN_HEAD = '微软雅黑'
MONO = 'Consolas'
SKIP_TOP = {'99-archive'}
BT = chr(96)

INLINE = re.compile(r'(\*\*.+?\*\*|' + BT + r'[^' + BT + r']+' + BT + r'|\[[^\]]+\]\([^)]+\))')


def set_font(run, name=CN, size=None, bold=None, italic=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rpr.insert(0, rf)
    for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
        rf.set(qn(a), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def add_runs(p, text, size=None, bold_all=False, base=CN):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith('**') and part.endswith('**') and len(part) >= 4:
            r = p.add_run(part[2:-2]); set_font(r, base, size, bold=True)
        elif part.startswith(BT) and part.endswith(BT) and len(part) >= 3:
            r = p.add_run(part[1:-1]); set_font(r, MONO, (size or 10.5) - 1)
        elif part.startswith('[') and '](' in part:
            label = part[1:part.index(']')]
            r = p.add_run(label); set_font(r, base, size, bold=(True if bold_all else None))
        else:
            r = p.add_run(part); set_font(r, base, size, bold=(True if bold_all else None))


def shade(p, fill='F5F5F5'):
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), fill)
    pPr.append(shd)


def border(p, edge='bottom', color='808080', sz='6'):
    pPr = p._p.get_or_add_pPr()
    pbdr = pPr.find(qn('w:pBdr'))
    if pbdr is None:
        pbdr = OxmlElement('w:pBdr'); pPr.append(pbdr)
    e = OxmlElement('w:' + edge)
    e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), sz)
    e.set(qn('w:space'), '1'); e.set(qn('w:color'), color)
    pbdr.append(e)


def add_field(p, instr, size=9, name=CN):
    r = p.add_run()
    b = OxmlElement('w:fldChar'); b.set(qn('w:fldCharType'), 'begin')
    i = OxmlElement('w:instrText'); i.set(qn('xml:space'), 'preserve'); i.text = instr
    s = OxmlElement('w:fldChar'); s.set(qn('w:fldCharType'), 'separate')
    t = OxmlElement('w:t'); t.text = '1'
    e = OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'), 'end')
    for el in (b, i, s, t, e):
        r._r.append(el)
    set_font(r, name, size)


def add_code(doc, line):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0); pf.space_after = Pt(0); pf.left_indent = Cm(0.4)
    r = p.add_run(line if line.strip() else '\u00a0')
    set_font(r, MONO, 9)
    shade(p)


def add_quote(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    try:
        p.style = doc.styles['Intense Quote']
    except KeyError:
        p.paragraph_format.left_indent = Cm(0.5)
    add_runs(p, text)
    for r in p.runs:
        r.font.color.rgb = RGBColor(0x40, 0x40, 0x40)


def list_para(doc, ordered, level):
    base = 'List Number' if ordered else 'List Bullet'
    name = base if level <= 1 else '%s %d' % (base, level)
    try:
        return doc.add_paragraph(style=name)
    except KeyError:
        p = doc.add_paragraph(style=base)
        p.paragraph_format.left_indent = Cm(0.74 * level)
        return p


def split_row(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    line = line.replace('\\|', '\x01')
    return [c.strip().replace('\x01', '|') for c in line.split('|')]


SEP = re.compile(r'^\s*\|?[\s:|\-]+\|?\s*$')


def is_sep(line):
    s = line.strip()
    return '-' in s and s.count('|') >= 2 and bool(SEP.match(s))


def add_table(doc, rows):
    ncol = max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=ncol)
    try:
        t.style = doc.styles['Table Grid']
    except KeyError:
        pass
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci in range(ncol):
            txt = row[ci] if ci < len(row) else ''
            cell = cells[ci]
            cell.text = ''
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            add_runs(p, txt, size=9.5, bold_all=(ri == 0))
    if rows:
        trPr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement('w:tblHeader'); th.set(qn('w:val'), 'true')
        trPr.append(th)
        for _row in t.rows:
            _trPr = _row._tr.get_or_add_trPr()
            _cs = OxmlElement('w:cantSplit'); _cs.set(qn('w:val'), 'true')
            _trPr.append(_cs)
    try:
        tblPr = t._tbl.tblPr
        w = OxmlElement('w:tblW'); w.set(qn('w:w'), '5000'); w.set(qn('w:type'), 'pct')
        tblPr.append(w)
        t.autofit = True
    except Exception:
        pass
    doc.add_paragraph()


def parse_cover(lines):
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    title = None
    if i < len(lines) and lines[i].strip().startswith('# '):
        title = lines[i].strip()[2:].strip()
        i += 1
    meta = []
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith('>'):
            meta.append(s[1:].strip()); i += 1
        elif not s:
            i += 1
        else:
            break
    while i < len(lines) and lines[i].strip() in ('---', '***', '___'):
        i += 1
    if title is None:
        title = '校园活动报名抽签与签到系统 —— 文档'
    return title, meta, lines[i:]


def build_cover(doc, title, meta):
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if ' —— ' in title:
        _a1, _b1 = title.split(' —— ', 1)
        r = p.add_run(_a1); set_font(r, CN_HEAD, 20, bold=True, color=(0x1F, 0x3B, 0x57))
        r.add_break()
        r2t = p.add_run(_b1); set_font(r2t, CN_HEAD, 20, bold=True, color=(0x1F, 0x3B, 0x57))
    else:
        r = p.add_run(title); set_font(r, CN_HEAD, 20, bold=True, color=(0x1F, 0x3B, 0x57))
    p2 = doc.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run('校园活动报名抽签与签到系统 · 轻型软件开发过程文档集')
    set_font(r2, CN, 11, color=(0x59, 0x59, 0x59))
    doc.add_paragraph()
    line = doc.add_paragraph(); line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    border(line)
    for m in meta:
        pm = doc.add_paragraph(); pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_runs(pm, m, size=10.5)
        for rr in pm.runs:
            rr.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
    doc.add_page_break()


def add_toc(doc):
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = h.add_run('目　录'); set_font(r, CN_HEAD, 16, bold=True, color=(0x1F, 0x3B, 0x57))
    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run()
    b = OxmlElement('w:fldChar'); b.set(qn('w:fldCharType'), 'begin')
    i = OxmlElement('w:instrText'); i.set(qn('xml:space'), 'preserve')
    i.text = 'TOC \\o "1-3" \\h \\z \\u'
    s = OxmlElement('w:fldChar'); s.set(qn('w:fldCharType'), 'separate')
    t = OxmlElement('w:t'); t.text = '（在 Word 中按 F9 更新目录）'
    e = OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'), 'end')
    for el in (b, i, s, t, e):
        run._r.append(el)
    set_font(run, CN, 10.5, color=(0x80, 0x80, 0x80))
    doc.add_page_break()


def setup(doc, title, meta):
    sec = doc.sections[0]
    sec.page_width = Cm(21.0); sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.54); sec.bottom_margin = Cm(2.54)
    sec.left_margin = Cm(2.8); sec.right_margin = Cm(2.8)
    normal = doc.styles['Normal']
    normal.font.name = CN
    normal.font.size = Pt(10.5)
    rpr = normal.element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rpr.insert(0, rf)
    for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
        rf.set(qn(a), CN)
    for _i in range(1, 5):
        try:
            st = doc.styles['Heading %d' % _i]
            st.font.name = CN_HEAD
            st.font.color.rgb = RGBColor(0x1F, 0x3B, 0x57)
            st.paragraph_format.keep_with_next = True
            rpr2 = st.element.get_or_add_rPr()
            rf2 = rpr2.find(qn('w:rFonts'))
            if rf2 is None:
                rf2 = OxmlElement('w:rFonts'); rpr2.insert(0, rf2)
            for _a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
                rf2.set(qn(_a), CN_HEAD)
        except KeyError:
            pass
    # 首页（封面）不显示页眉页脚
    sec.different_first_page_header_footer = True
    hdr = sec.header.paragraphs[0]
    hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hr = hdr.add_run(title[:44])
    set_font(hr, CN, 8.5, color=(0x80, 0x80, 0x80))
    border(hdr, 'bottom', 'BFBFBF', '4')
    ft = sec.footer.paragraphs[0]
    ft.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = ft.add_run('第 '); set_font(rr, CN, 9, color=(0x59, 0x59, 0x59))
    add_field(ft, 'PAGE')
    rr = ft.add_run(' 页 / 共 '); set_font(rr, CN, 9, color=(0x59, 0x59, 0x59))
    add_field(ft, 'NUMPAGES')
    rr = ft.add_run(' 页'); set_font(rr, CN, 9, color=(0x59, 0x59, 0x59))
    # 文档属性 + 打开时更新域
    try:
        cp = doc.core_properties
        cp.title = title
        cp.author = '校园活动报名抽签与签到系统项目组'
        cp.subject = '轻型软件开发过程文档集'
        cp.comments = ' | '.join(meta)[:255]
    except Exception:
        pass
    try:
        uf = OxmlElement('w:updateFields'); uf.set(qn('w:val'), 'true')
        doc.settings.element.append(uf)
    except Exception:
        pass


def render_body(doc, lines):
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith(BT * 3):
            i += 1
            while i < n and not lines[i].strip().startswith(BT * 3):
                add_code(doc, lines[i].rstrip()); i += 1
            i += 1
            continue
        if not s:
            i += 1; continue
        if s.startswith('|') and '|' in s[1:]:
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                if is_sep(lines[i]):
                    i += 1; continue
                rows.append(split_row(lines[i])); i += 1
            if rows:
                add_table(doc, rows)
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', s)
        if m:
            level = min(len(m.group(1)) - 1, 4)
            h = doc.add_heading('', level=level)
            h.paragraph_format.keep_with_next = True
            add_runs(h, m.group(2).strip(), base=CN_HEAD)
            for r in h.runs:
                r.bold = True
            i += 1; continue
        if s.startswith('>'):
            add_quote(doc, s[1:].strip()); i += 1; continue
        if re.match(r'^[-*+]\s+', s):
            indent = len(line) - len(line.lstrip())
            p = list_para(doc, False, 1 + min(indent // 2, 2))
            add_runs(p, re.sub(r'^[-*+]\s+', '', s)); i += 1; continue
        if re.match(r'^\d+\.\s+', s):
            indent = len(line) - len(line.lstrip())
            p = list_para(doc, True, 1 + min(indent // 2, 2))
            add_runs(p, re.sub(r'^\d+\.\s+', '', s)); i += 1; continue
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', s):
            i += 1; continue
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        add_runs(p, s)
        i += 1


def convert(src, dst):
    with open(src, encoding='utf-8') as f:
        lines = f.read().splitlines()
    title, meta, body = parse_cover(lines)
    doc = Document()
    setup(doc, title, meta)
    build_cover(doc, title, meta)
    if sum(1 for l in body if l.strip().startswith('## ')) >= 3:
        add_toc(doc)
    render_body(doc, body)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    doc.save(dst)


def collect():
    items = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        head = rel.split(os.sep)[0]
        if head in SKIP_TOP:
            dirnames[:] = []
            continue
        for fn in sorted(filenames):
            if not fn.endswith('.md'):
                continue
            src = os.path.join(dirpath, fn)
            if rel == '.' and fn == 'README.md':
                dst = os.path.join(ROOT, 'documentation-index.docx')
            else:
                dst = os.path.join(dirpath, fn[:-3] + '.docx')
            items.append((src, dst))
    return items


def main():
    items = collect()
    for src, dst in items:
        convert(src, dst)
        print('OK  %-52s -> %s' % (os.path.relpath(src, ROOT), os.path.relpath(dst, ROOT)))
    print('TOTAL', len(items))


if __name__ == '__main__':
    main()
