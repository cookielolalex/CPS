"""Read-only complete saved-cell fidelity against writer's own assembly matrix."""
from pathlib import Path
import argparse,json,zipfile,xml.etree.ElementTree as E,hashlib,math
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def col(n):
    s=''
    while n:n,a=divmod(n-1,26);s=chr(65+a)+s
    return s
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    d=Path(a.output).resolve(strict=True);book=d/'research-draft.xlsx'
    expected=json.loads((d/'EXPECTED_SAVED_VALUES.json').read_text(encoding='utf-8'))['sheets']
    errors=[];counts=[]
    with zipfile.ZipFile(book) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(t.text or '' for t in si.iter('{'+NS['m']+'}t')) for si in E.fromstring(z.read('xl/sharedStrings.xml'))]
        wb=E.fromstring(z.read('xl/workbook.xml'))
        rel={r.attrib['Id']:r.attrib['Target'] for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        sheets=wb.find('m:sheets',NS)
        if [s.attrib['name'] for s in sheets]!=[s['name'] for s in expected]:raise ValueError('SHEET_SEQUENCE_MISMATCH')
        for sheet,exp in zip(sheets,expected):
            target=rel[sheet.attrib['{'+NS['r']+'}id']]
            target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            root=E.fromstring(z.read(target));cells={};formulas=[]
            for c in root.findall('.//m:sheetData/m:row/m:c',NS):
                addr=c.attrib['r'];typ=c.attrib.get('t','n');v=c.find('m:v',NS)
                if c.find('m:f',NS) is not None:formulas.append(addr)
                if typ=='s':value=shared[int(v.text)]
                elif typ=='inlineStr':value=''.join(t.text or '' for t in c.findall('.//m:t',NS))
                elif typ=='b':value=v is not None and v.text=='1'
                elif typ in ('str','e'):value=v.text if v is not None else None
                else:value=float(v.text) if v is not None and v.text is not None else None
                cells[addr]=value
            if formulas:errors.append({'sheet':exp['name'],'formulas':formulas})
            checked=0;nonempty=0
            for i,row in enumerate(exp['values'],1):
                for j,want in enumerate(row,1):
                    addr=f'{col(j)}{i}';got=cells.pop(addr,None);checked+=1
                    if want is not None:nonempty+=1
                    good=(got is None if want is None else isinstance(got,str) and got==want if isinstance(want,str) else type(got) in (int,float) and math.isfinite(got) and got==want)
                    if not good:errors.append({'sheet':exp['name'],'cell':addr,'expected_type':type(want).__name__,'actual_type':type(got).__name__,'expected':want,'actual':got})
            extra={k:v for k,v in cells.items() if v is not None}
            if extra:errors.append({'sheet':exp['name'],'unexpected_populated_cells':extra})
            counts.append({'sheet':exp['name'],'rows':len(exp['values']),'checked_cells':checked,'nonempty_cells':nonempty,'formula_count':len(formulas)})
        for name in z.namelist():
            if name.endswith('.rels'):
                for r in E.fromstring(z.read(name)):
                    if r.attrib.get('TargetMode')=='External':errors.append({'external_relationship':name,'target':r.attrib.get('Target')})
    report={'status':'SAVED_ALL_CELL_VALUE_TYPE_PASS' if not errors else 'SAVED_ALL_CELL_VALUE_TYPE_FAILED','xlsx_sha256':hashlib.sha256(book.read_bytes()).hexdigest(),'sheets':counts,'errors':errors,'scope':'Assembly fidelity to untouched carrier-derived writer matrix; not independent source semantics','native_excel_validation':False}
    with (d/'SAVED_FILE_QA.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
