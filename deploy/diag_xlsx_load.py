"""Find what makes a LibreOffice build refuse to load an .xlsx ("Error: source file could not be loaded").

A diagnostic for the operator VM. It writes only to a new work folder and never changes the input. It converts:
  1. the input as it is;
  2. the input with the Excel 2007-365 import filter forced (--infilter), to separate type detection from import;
  3. the input re-saved by openpyxl (structure rewritten, content kept);
  4. each sheet alone; then, for a failing sheet, halves of its rows down to one row, then halves of that row's cells
     down to one cell (each variant keeps the sheet's column widths).
It reports every attempt and, at the end, the smallest failing variant: the sheet, the cell and the cell value with
its code points. Usage:
  python3 deploy/diag_xlsx_load.py FILE.xlsx WORKDIR [--soffice soffice]
Exit 0 when the input loads, 1 when a smallest failing variant was found, 3 when it fails but no smaller variant does.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata

import openpyxl
from openpyxl.utils import get_column_letter


def convert(soffice, path, workdir, label, infilter=None):
    out = tempfile.mkdtemp(prefix='out_', dir=workdir)
    home = tempfile.mkdtemp(prefix='home_', dir=workdir)
    cmd = [soffice, '--headless']
    if infilter:
        cmd.append(f'--infilter={infilter}')
    cmd += ['--convert-to', 'pdf', '--outdir', out, path]
    start = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=300,
                           env=dict(os.environ, HOME=home))
        rc, so, se = r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        rc, so, se = 'timeout', '', ''
    ok = rc == 0 and any(f.endswith('.pdf') for f in os.listdir(out))
    msg = ' | '.join(x.splitlines()[-1] for x in (so, se) if x)
    print(f'[{"LOADS" if ok else "FAILS"}] {label}: exit {rc} in {time.time() - start:.0f} s{"; " + msg[:300] if msg else ""}',
          flush=True)
    shutil.rmtree(home, ignore_errors=True)
    return ok


def build(src_wb, sheet_title, rows, cols, path):
    """A one-sheet workbook with the given rows (1-based indexes) and columns of one source sheet, at their places."""
    ws_src = src_wb[sheet_title]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    for c in cols:
        letter = get_column_letter(c)
        if letter in ws_src.column_dimensions and ws_src.column_dimensions[letter].width:
            ws.column_dimensions[letter].width = ws_src.column_dimensions[letter].width
    for r in rows:
        for c in cols:
            v = ws_src.cell(row=r, column=c).value
            if v is not None:
                ws.cell(row=r, column=c, value=v)
    wb.save(path)


def describe(v):
    if not isinstance(v, str):
        return repr(v)
    cps = ' '.join(f'U+{ord(ch):04X}' for ch in v if ord(ch) > 0x7e or ord(ch) < 0x20)
    odd = [f'U+{ord(ch):04X} {unicodedata.name(ch, "?")}' for ch in v
           if unicodedata.category(ch)[0] in 'CZ' and ch != ' ']
    return f'{v!r} (length {len(v)}; non-ASCII code points: {cps or "none"}; control/space-like: {odd or "none"})'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('workdir')
    ap.add_argument('--soffice', default='soffice')
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=False)
    src = os.path.abspath(a.file)
    work = os.path.abspath(a.workdir)
    n = [0]

    def variant(name):
        n[0] += 1
        return os.path.join(work, f'v{n[0]:02d}_{name}.xlsx')

    if convert(a.soffice, src, work, 'input as it is'):
        print('RESULT: the input loads; nothing to narrow down.')
        return 0
    convert(a.soffice, src, work, 'input with --infilter="Calc MS Excel 2007 XML"', infilter='Calc MS Excel 2007 XML')
    wb = openpyxl.load_workbook(src)
    p = variant('resaved')
    wb.save(p)
    convert(a.soffice, p, work, 'input re-saved by openpyxl')

    culprit = None
    for ws in wb.worksheets:
        rows = list(range(1, ws.max_row + 1))
        cols = list(range(1, ws.max_column + 1))
        p = variant('sheet')
        build(wb, ws.title, rows, cols, p)
        if convert(a.soffice, p, work, f'sheet {ws.title!r} alone ({ws.max_row}x{ws.max_column})'):
            continue
        # halve the rows while a half fails
        while len(rows) > 1:
            half = len(rows) // 2
            for part in (rows[:half], rows[half:]):
                p = variant('rows')
                build(wb, ws.title, part, cols, p)
                if not convert(a.soffice, p, work, f'sheet {ws.title!r} rows {part[0]}-{part[-1]}'):
                    rows = part
                    break
            else:
                break   # each half loads: the failure needs rows from both halves
        # then halve the columns
        while len(cols) > 1:
            half = len(cols) // 2
            for part in (cols[:half], cols[half:]):
                p = variant('cols')
                build(wb, ws.title, rows, part, p)
                if not convert(a.soffice, p, work, f'sheet {ws.title!r} rows {rows[0]}-{rows[-1]} '
                                                   f'columns {get_column_letter(part[0])}-{get_column_letter(part[-1])}'):
                    cols = part
                    break
            else:
                break
        culprit = (ws, rows, cols)
        break

    if culprit is None:
        print('RESULT: the input fails, but every sheet loads alone: the failure needs more than one sheet.')
        return 3
    ws, rows, cols = culprit
    print(f'RESULT: smallest failing variant: sheet {ws.title!r}, rows {rows[0]}-{rows[-1]}, '
          f'columns {get_column_letter(cols[0])}-{get_column_letter(cols[-1])}')
    for r in rows:
        for c in cols:
            v = ws.cell(row=r, column=c).value
            if v is not None:
                print(f'  {get_column_letter(c)}{r}: {describe(v)}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
