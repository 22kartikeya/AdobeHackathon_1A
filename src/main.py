import fitz                         # PyMuPDF
import pdfplumber
import re, json, os
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Tuple

# ──────────────────────────────────────────────────────────  geometry helper
try:
    from shapely.geometry import box
    def intersects(a: Tuple[float, float, float, float],
                   b: Tuple[float, float, float, float]) -> bool:
        return box(*a).intersects(box(*b))
except Exception:                           # pure-Python fallback
    def intersects(a, b):
        ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
        return not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)

# ──────────────────────────────────────────────────────────  tiny container
class Line:
    __slots__ = ('text', 'size', 'page', 'bbox')
    def __init__(self, text, size, page, bbox):
        self.text, self.size, self.page, self.bbox = text, size, page, bbox

# ──────────────────────────────────────────────────────────  low-level read
def read_lines(pdf_path: str) -> List[Line]:
    doc, out = fitz.open(pdf_path), []
    for p_idx, page in enumerate(doc, 1):
        for blk in page.get_text('dict')['blocks']:
            for ln in blk.get('lines', []):
                spans = ln['spans']
                if not spans:        continue
                txt = ' '.join(s['text'] for s in spans).strip()
                if not txt:          continue
                size = round(max(s['size'] for s in spans))
                x0, y0, x1, y1 = spans[0]['bbox']
                for s in spans[1:]:
                    sx0, sy0, sx1, sy1 = s['bbox']
                    x0, y0 = min(x0, sx0), min(y0, sy0)
                    x1, y1 = max(x1, sx1), max(y1, sy1)
                out.append(Line(txt, size, p_idx, (x0, y0, x1, y1)))
    doc.close()
    return out

# ──────────────────────────────────────────────────────────  table bboxes
def table_bboxes(pdf_path: str, n_pages: int):
    boxes = [[] for _ in range(n_pages)]
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, p in enumerate(pdf.pages):
                if i >= n_pages: break
                boxes[i] = [t.bbox for t in (p.find_tables() or [])]
    except Exception:
        pass
    return boxes

# ──────────────────────────────────────────────────────────  title
def title_from(lines: List[Line]) -> str:
    page1 = [l for l in lines if l.page == 1]
    if not page1: return ''
    top   = max(l.size for l in page1)
    parts = [l.text.strip() for l in page1 if l.size == top]
    out, seen = [], set()
    for t in parts:
        if t not in seen:
            seen.add(t); out.append(t)
    return ' '.join(out)

# ──────────────────────────────────────────────────────────  cleaning
def clean(lines: List[Line], pdf: str) -> List[Line]:
    if not lines: return []
    pg_cnt   = max(l.page for l in lines)
    tables   = table_bboxes(pdf, pg_cnt)
    hdr_pct, max_chars = 0.10, 150

    per_page = defaultdict(list)
    for l in lines: per_page[l.page].append(l)

    seen, out = set(), []
    for pg, ln_list in per_page.items():
        h      = max(l.bbox[3] for l in ln_list)
        top,bt = h*hdr_pct, h*(1-hdr_pct)
        tboxes = tables[pg-1] if pg-1 < len(tables) else []
        for ln in ln_list:
            if len(ln.text) > max_chars or ln.text == '•':         continue
            if ln.bbox[1] < top or ln.bbox[3] > bt:                continue
            if any(intersects(ln.bbox, tb) for tb in tboxes):       continue
            key = (ln.text.lower().strip(), round(ln.bbox[0],1))
            if key in seen:                                         continue
            seen.add(key); out.append(ln)
    return out

# ──────────────────────────────────────────────────────────  outline logic
NUM_RE   = re.compile(r'^(\d+(?:\.\d+)*)\s+')          # 1. / 1.2 / 1.2.3
COLON_RE = re.compile(r'.+:$')

def detect_outline(lines: List[Line]) -> List[dict]:
    if not lines: return []

    #  small, purely numbered two-page forms  →  no outline
    if len({l.page for l in lines}) <= 2 and all(NUM_RE.match(l.text) for l in lines):
        return []

    body      = Counter(l.size for l in lines).most_common(1)[0][0]
    head_sizes= [s for s,_ in Counter(l.size for l in lines
                            if l.size >= body*1.15).most_common(4)]
    head_sizes.sort(reverse=True)                       # largest → H1
    size2lvl  = {s: f'H{idx+1}' for idx,s in enumerate(head_sizes)}

    cands = []
    for ln in lines:
        txt = ln.text.strip()
        if ln.size < body*1.05:                              continue
        if len(txt) > 150 and not NUM_RE.match(txt):        continue
        if (len(txt.split()) > 3 and
            txt.split()[0][0].islower() and
            not NUM_RE.match(txt)):
            continue
        if (ln.size in size2lvl or NUM_RE.match(txt) or
            COLON_RE.search(txt)):
            cands.append(ln)

    # build outline, allow short-line merging
    outline, i = [], 0
    while i < len(cands):
        ln  = cands[i]
        txt = ln.text.strip()

        # merge rule: if next heading is ≤2 words & on same page, append
        if (i+1 < len(cands) and
            cands[i+1].page == ln.page and
            len(cands[i+1].text.split()) <= 2):
            txt = txt + ' ' + cands[i+1].text.strip()
            i += 1                                           # skip next

        # level
        if m := NUM_RE.match(txt):
            lvl = f'H{min(m.group(1).count(".")+1,4)}'
        elif COLON_RE.search(txt):
            lvl = 'H3'
        else:
            lvl = size2lvl.get(ln.size, 'H3')

        outline.append({'level': lvl, 'text': txt, 'page': ln.page})
        i += 1

    # deduplicate (text, level)
    seen, final = set(), []
    for h in outline:
        k = (h['text'].lower(), h['level'])
        if k not in seen:
            seen.add(k); final.append(h)
    return final

# ──────────────────────────────────────────────────────────  logical pages
def logical_shift(outl: List[dict]):
    if not outl: return
    first = min(o['page'] for o in outl)
    shift = 0 if first == 1 else -(first - 2)
    for o in outl:
        o['page'] = max(1, o['page'] + shift)

# ──────────────────────────────────────────────────────────  driver
def extract(pdf_path: Path, out_dir: Path):
    raw   = read_lines(str(pdf_path))
    title = title_from(raw)

    lines = clean(raw, str(pdf_path))
    outln = detect_outline(lines)
    logical_shift(outln)

    out_dir.mkdir(exist_ok=True, parents=True)
    with (out_dir / pdf_path.with_suffix('.json').name).open('w', encoding='utf-8') as fh:
        json.dump({'title': title, 'outline': outln}, fh,
                  indent=2, ensure_ascii=False)
    print(f'✓ {pdf_path.name:25s} {len(outln):3d} headings')

def main():
    in_dir  = Path('app/input')
    out_dir = Path('app/output')
    for pdf in sorted(in_dir.glob('*.pdf')):
        try:
            extract(pdf, out_dir)
        except Exception as e:
            print('✗', pdf.name, e)

if __name__ == '__main__':
    main()
