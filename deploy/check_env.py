"""CPS environment check. Records tool versions, paths and the node binary sha256; reads no case data.
Usage: python3 deploy/check_env.py --out ENV_REPORT.json [--node /abs/path/to/node]"""
import argparse, hashlib, json, os, platform, shutil, subprocess, sys, datetime

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else ''
    except Exception as e:
        return f'ERROR {e.__class__.__name__}'

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--node')
    a = ap.parse_args()
    r = {'schema': 'cps.env-report.v1', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'platform': platform.platform(), 'python': sys.version.split()[0], 'python_executable': sys.executable}
    need = {}
    for mod, want in (('openpyxl', '3.1.5'), ('xlrd', '2.0.2'), ('lxml', '')):
        try:
            m = __import__(mod); v = getattr(m, '__version__', None) or getattr(getattr(m, 'etree', None), '__version__', '')
            if mod == 'lxml':
                from lxml import etree; v = '.'.join(map(str, etree.LXML_VERSION))
            r[mod] = v; need[mod] = (v.startswith(want) if want else True)
        except Exception as e:
            r[mod] = f'MISSING ({e.__class__.__name__})'; need[mod] = False
    node = a.node or shutil.which('node')
    if node:
        real = os.path.realpath(node)
        r['node'] = {'command': node, 'realpath': real, 'version': run([real, '--version']), 'sha256': sha(real)}
        need['node_v22'] = r['node']['version'].startswith('v22.')
    else:
        r['node'] = 'MISSING'; need['node_v22'] = False
    so = shutil.which('soffice') or shutil.which('libreoffice')
    r['libreoffice'] = {'path': so, 'version': run([so, '--version'])} if so else 'MISSING'
    need['libreoffice'] = bool(so)
    pt = shutil.which('pdftoppm')
    r['pdftoppm'] = {'path': pt, 'version': run([pt, '-v'])} if pt else 'MISSING'
    need['pdftoppm'] = bool(pt)
    fc = shutil.which('fc-list')
    r['cjk_fonts'] = (run(['sh', '-c', 'fc-list :lang=zh-tw family | head -3']) if fc else 'fc-list missing')
    need['cjk_fonts'] = bool(fc) and bool(r['cjk_fonts']) and 'missing' not in r['cjk_fonts']
    r['python_ok'] = sys.version_info >= (3, 11); need['python_3_11'] = r['python_ok']
    r['requirements_met'] = need
    r['all_met'] = all(need.values())
    open(a.out, 'w', encoding='utf-8').write(json.dumps(r, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'all_met': r['all_met'], 'missing': [k for k, v in need.items() if not v],
                      'node_sha256': r['node']['sha256'] if isinstance(r['node'], dict) else None}))

if __name__ == '__main__':
    main()
