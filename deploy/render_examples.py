"""Render the interview example excerpts (.xlsx) to PNG on the operator VM, the same way the interview kit did:
LibreOffice headless -> PDF -> pdftoppm 120 dpi -> each page trimmed to content (16 px margin) -> pages stacked.
Reads only the excerpt files given. Usage: python3 deploy/render_examples.py EXAMPLES_DIR"""
import glob, os, subprocess, sys, tempfile
from PIL import Image, ImageChops

def render(xp, outdir):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', tmp, xp], check=True, capture_output=True)
        pdf = glob.glob(tmp + '/*.pdf')[0]
        subprocess.run(['pdftoppm', '-r', '120', '-png', pdf, tmp + '/p'], check=True)
        ims = []
        for p in sorted(glob.glob(tmp + '/p*.png')):
            im = Image.open(p).convert('RGB')
            bbox = ImageChops.difference(im, Image.new('RGB', im.size, (255, 255, 255))).getbbox()
            if bbox:
                im = im.crop((max(0, bbox[0] - 16), max(0, bbox[1] - 16), min(im.width, bbox[2] + 16), min(im.height, bbox[3] + 16)))
            ims.append(im)
        w, h = max(i.width for i in ims), sum(i.height for i in ims)
        out = Image.new('RGB', (w, h), (255, 255, 255)); y = 0
        for i in ims:
            out.paste(i, (0, y)); y += i.height
        pp = os.path.join(outdir, os.path.basename(xp)[:-5] + '.png'); out.save(pp, optimize=True)
        return pp, len(ims), out.size

if __name__ == '__main__':
    d = sys.argv[1]
    xs = sorted(glob.glob(os.path.join(d, '*.xlsx')))
    for xp in xs:
        pp, n, size = render(xp, d)
        print(os.path.basename(pp), n, 'page(s)', size)
    print(len(xs), 'rendered')
