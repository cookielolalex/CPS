"""Render the interview example excerpts (.xlsx) to PNG on the operator VM, the same way the interview kit did:
LibreOffice headless -> PDF -> pdftoppm 120 dpi -> each page trimmed to content (16 px margin) -> pages stacked.
Reads only the excerpt files given.

Usage: python3 deploy/render_examples.py EXAMPLES_DIR [NAME.xlsx ...]
  With names, only those files are rendered (for example the ones a failed run did not finish).
  Every file is tried; a file that fails is reported with LibreOffice's own output (its exit code, stdout and the
  last lines of stderr), and the run ends with exit 1 and the list of failed files. An existing PNG is replaced.
"""
import glob, os, subprocess, sys, tempfile
from PIL import Image, ImageChops


class RenderError(Exception):
    pass


def _tail(text, lines=25):
    return '\n'.join(text.strip().splitlines()[-lines:])


def render(xp, outdir):
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', tmp, xp], capture_output=True,
                           text=True, errors='replace', timeout=600)
        pdfs = glob.glob(tmp + '/*.pdf')
        if r.returncode != 0 or not pdfs:
            raise RenderError(f'soffice exit {r.returncode}, {len(pdfs)} PDF(s)\n--- soffice stdout ---\n{_tail(r.stdout)}'
                              f'\n--- soffice stderr (last lines) ---\n{_tail(r.stderr)}')
        p = subprocess.run(['pdftoppm', '-r', '120', '-png', pdfs[0], tmp + '/p'], capture_output=True, text=True,
                           errors='replace', timeout=600)
        if p.returncode != 0:
            raise RenderError(f'pdftoppm exit {p.returncode}\n{_tail(p.stderr)}')
        ims = []
        for f in sorted(glob.glob(tmp + '/p*.png')):
            im = Image.open(f).convert('RGB')
            bbox = ImageChops.difference(im, Image.new('RGB', im.size, (255, 255, 255))).getbbox()
            if bbox:
                im = im.crop((max(0, bbox[0] - 16), max(0, bbox[1] - 16), min(im.width, bbox[2] + 16), min(im.height, bbox[3] + 16)))
            ims.append(im)
        if not ims:
            raise RenderError('pdftoppm produced no page images')
        w, h = max(i.width for i in ims), sum(i.height for i in ims)
        out = Image.new('RGB', (w, h), (255, 255, 255)); y = 0
        for i in ims:
            out.paste(i, (0, y)); y += i.height
        pp = os.path.join(outdir, os.path.basename(xp)[:-5] + '.png'); out.save(pp, optimize=True)
        return pp, len(ims), out.size


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    d = argv[1]
    if len(argv) > 2:
        xs = [os.path.join(d, n) for n in argv[2:]]
        missing = [x for x in xs if not os.path.isfile(x)]
        if missing:
            print('not found: ' + ', '.join(missing), file=sys.stderr)
            return 2
    else:
        xs = sorted(glob.glob(os.path.join(d, '*.xlsx')))
    failed = []
    for xp in xs:
        try:
            pp, n, size = render(xp, d)
            print(os.path.basename(pp), n, 'page(s)', size, flush=True)
        except (RenderError, subprocess.TimeoutExpired, OSError) as e:
            failed.append(os.path.basename(xp))
            print(f'FAILED {os.path.basename(xp)}: {e}', flush=True)
    print(f'{len(xs) - len(failed)} of {len(xs)} rendered' + (f'; failed: {", ".join(failed)}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
