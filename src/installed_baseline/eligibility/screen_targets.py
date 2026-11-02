"""Read-only eligibility screen. No target value is a generation input or gold approval."""
import argparse, csv, hashlib, json, re, subprocess, sys, time, unicodedata
from collections import Counter
from pathlib import Path
from datetime import datetime
import openpyxl

VERSION='1.7'
SKIP_SHEET=re.compile(r'原材料清單|原始|已填|OK|電機|板金|鈑金|生管|沖孔',re.I)
SKIP_FILE=re.compile(r'已填|(?<![A-Za-z])OK(?![A-Za-z])',re.I)
ENCLOSURE=re.compile(r'(?i)\bCASE\b|箱體|配電箱|電話配線箱|控制箱|電控箱|電表箱|儀表箱|接線箱|端子箱|接線盒|機箱|盤體|配電盤|控制盤|電源箱|電錶箱|動力箱|配線箱|弱電箱|合併箱|電話箱|分電箱|電信箱|自立盤')
UNRELATED=re.compile(r'(?i)NFB|AUX|FL\s*\+\s*LS|\d+C\s*\+\s*\d+G|銅排|母排|BUSBAR|Cu\s*bus\s*\+\s*Support')
LABOUR=re.compile(r'工資|工料|安裝|製作|加工')
AXIS=re.compile(r'(?i)[WHD]|寬|高|深')
NUMPLUS=re.compile(r'\d+(?:\.\d+)?\s*(?:[WHD]|cm|mm|公分|公厘|[)）])?\s*\+\s*(?:[WHD]\s*)?\(?\s*\d+(?:\.\d+)?',re.I)
FORMATS={'.xlsx','.xlsm','.xls'}

def norm(v):
    return unicodedata.normalize('NFKC',str(v or '')).strip()

def classify_plus(value,role,enclosure=False):
    s=norm(value)
    if '+' not in s:return 'NONE'
    numeric=bool(NUMPLUS.search(s))
    # Tie the numeric addition to an adjacent dimension axis or multiplication,
    # rather than an arbitrary W/H/D letter elsewhere in an equipment sentence.
    dimensions=False
    for hit in NUMPLUS.finditer(s):
        token=hit.group(0);before=s[:hit.start()];after=s[hit.end():]
        axis_in_token=bool(re.search(r'\d\s*[WHD]\s*\+|\+\s*[WHD]\s*\d',token,re.I))
        axis_before=bool(re.search(r'(?:[WHD]|寬|高|深)\s*[:=]?\s*\(?\s*$',before,re.I))
        axis_after=bool(re.match(r'\s*\)?\s*(?:cm|mm)?\s*(?:[WHD](?![A-Za-z])|寬|高|深)',after,re.I))
        product_before=bool(re.search(r'\d\s*(?:[WHD]|cm|mm)?\s*[*x×]\s*(?:[WHD]\s*)?\(?\s*$',before,re.I))
        product_after=bool(re.match(r'\s*\)?\s*(?:[WHD]|cm|mm)?\s*[*x×]\s*(?:[WHD]\s*)?\d',after,re.I))
        if axis_in_token or axis_before or axis_after or product_before or product_after:dimensions=True;break
    if (role=='panel_spec' or enclosure) and numeric and dimensions:return 'QUALIFYING'
    if numeric and dimensions:return 'AMBIGUOUS'
    if UNRELATED.search(s):return 'NONQUALIFYING'
    if LABOUR.search(s) and not numeric:return 'NONQUALIFYING'
    if (role=='panel_spec' or enclosure):return 'AMBIGUOUS'
    return 'NONQUALIFYING'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def header_map(row):
    m={}
    for i,c in enumerate(row):
        s=re.sub(r'\s+','',norm(c.value))
        if s in ('盤體名稱','盤名稱','盤名'):m['panel_name']=i
        elif s in ('盤體規格','盤規格','盤體尺寸','箱體尺寸'):m['panel_spec']=i
        elif s in ('材料名稱','品名','材料品名'):m['material_name']=i
        elif s in ('規格','材料規格','規格尺寸','規格+材料名稱'):m['material_spec']=i
        elif s=='單位':m['unit']=i
        elif s=='數量':m['quantity']=i
    if 'material_name' in m and 'material_spec' in m and ('unit' in m or 'quantity' in m or 'panel_spec' in m):return m
    return None

def scan(path,deadline):
    p=Path(path)
    r={'path':str(p),'sha256':None,'hash_unchanged':None,'coverage_complete':False,'status':'REVIEW_REQUIRED','reasons':[],
       'qualifying_evidence':[],'ambiguous_evidence':[],'nonqualifying_plus_observations':[],
       'nonqualifying_plus_count':0,'sheets':[],'eligibility_is_not_gold':True}
    # Name controls occur before opening contents or computing a content hash.
    if p.name.startswith('~$') or p.suffix.lower() in ('.tmp','.temp') or SKIP_FILE.search(p.name):
        r['status']='SKIPPED_KNOWN_LATER_STAGE_OR_TEMP';r['reasons']=['Filename excluded before content access'];return r
    if p.suffix.lower() not in FORMATS:
        r['status']='UNSCANNED_FORMAT';r['reasons']=['Unsupported non-spreadsheet discovery file'];return r
    if not p.is_file():r['reasons']=['Missing target path'];return r
    try:
        r['sha256']=sha(p);r['file_size']=p.stat().st_size;r['mtime_ns']=p.stat().st_mtime_ns
        ids=re.findall(r'(?<!\d)(1\d{6})(?!\d)',str(p));r['project_id_path_metadata']=ids[-1] if ids else None
        if p.suffix.lower()=='.xls':r['reasons']=['Legacy XLS is not supported by this screener; review required'];return r
        book=openpyxl.load_workbook(p,read_only=True,data_only=True,keep_links=False)
        formulas=openpyxl.load_workbook(p,read_only=True,data_only=False,keep_links=False)
        try:
            recognized=0
            for ws in book.worksheets:
                if time.monotonic()>deadline:raise TimeoutError('Finite scan deadline reached')
                if SKIP_SHEET.search(ws.title):
                    r['sheets'].append({'name':ws.title,'status':'SKIPPED_FORBIDDEN_BEFORE_CELL_ACCESS'});continue
                sm={'name':ws.title,'status':'REVIEW_REQUIRED','rows_scanned':0}
                r['sheets'].append(sm)
                ws.reset_dimensions(); fw=formulas[ws.title];fw.reset_dimensions()
                m=None;hr=None;first30_nonblank=False
                for header_index,row in enumerate(ws.iter_rows(min_row=1,max_row=30,max_col=64),1):
                    first30_nonblank=first30_nonblank or any(c.value not in (None,'') for c in row)
                    found=header_map(row)
                    if found:m=found;hr=header_index;break
                if m is None:
                    # A first-30-row blank prefix is not proof of an empty sheet.
                    # Only label EMPTY after both complete saved-value and formula
                    # streams finish, including cells outside the header window.
                    empty=not first30_nonblank
                    if empty:
                        for source_ws in (ws,fw):
                            for nr,unknownrow in enumerate(source_ws.iter_rows(),1):
                                if nr>30000 or time.monotonic()>deadline:
                                    empty=False;sm['empty_check_incomplete']=True;break
                                if any(c.value not in (None,'') for c in unknownrow):empty=False;break
                            if not empty:break
                    if empty:
                        sm['status']='EMPTY_COMPLETE_VALUE_AND_FORMULA_STREAMS';continue
                    r['reasons'].append('Unrecognized sheet schema: '+ws.title);continue
                recognized+=1;sm.update({'status':'SCANNED_RECOGNIZED_SUPPLY','header_row':hr,
                    'mapped_columns':{k:openpyxl.utils.get_column_letter(v+1) for k,v in m.items()}})
                maxcol=max(m.values())+1;previous_enclosure=False;last_context={}
                for row,frow in zip(ws.iter_rows(min_row=hr+1,max_col=maxcol),fw.iter_rows(min_row=hr+1,max_col=maxcol)):
                    sm['rows_scanned']+=1
                    if sm['rows_scanned']>30000:raise RuntimeError('Row cap reached; incomplete scan')
                    if sm['rows_scanned']%200==0 and time.monotonic()>deadline:raise TimeoutError('Finite scan deadline reached')
                    vals={k:row[v].value for k,v in m.items()}
                    material=norm(vals.get('material_name'))
                    is_enclosure=bool(ENCLOSURE.search(material)) if material else previous_enclosure
                    if material:previous_enclosure=is_enclosure
                    context={k:vals.get(k) for k in ('panel_name','panel_spec','material_name','material_spec') if vals.get(k) is not None}
                    if material:last_context={'material_name':vals.get('material_name')}
                    for role in ('panel_name','panel_spec','material_name','material_spec'):
                        if role not in m:continue
                        i=m[role];c=row[i];fc=frow[i]
                        if fc.data_type=='f' and c.value is None:
                            r['reasons'].append('Missing relevant formula cache: '+ws.title+'!'+fc.coordinate)
                            r['ambiguous_evidence'].append({'sheet':ws.title,'cell':fc.coordinate,'raw_formula':fc.value,'reason':'Missing saved cache in source identification/dimension column'});continue
                        if c.data_type=='e':
                            r['reasons'].append('Source-column error cell: '+ws.title+'!'+c.coordinate);continue
                        if '+' not in norm(c.value):continue
                        classification=classify_plus(c.value,role,is_enclosure)
                        evidence={'sheet':ws.title,'cell':c.coordinate,'role':role,'raw_value':c.value,
                                  'context':context,'enclosure_continuation':bool(not material and is_enclosure),
                                  'previous_enclosure_context':last_context if not material and is_enclosure else None}
                        if classification=='QUALIFYING':r['qualifying_evidence'].append(evidence)
                        elif classification=='AMBIGUOUS':r['ambiguous_evidence'].append(evidence)
                        else:
                            r['nonqualifying_plus_count']+=1
                            if len(r['nonqualifying_plus_observations'])<50:r['nonqualifying_plus_observations'].append(evidence)
            if not recognized:r['reasons'].append('No recognized permitted supply sheet')
            r['coverage_complete']=recognized>0 and all(s['status']!='REVIEW_REQUIRED' for s in r['sheets'])
        finally:book.close();formulas.close()
        r['hash_unchanged']=sha(p)==r['sha256']
        if not r['hash_unchanged']:r['reasons'].append('Source hash changed during scan')
        if not r['hash_unchanged']:r['status']='REVIEW_REQUIRED'
        elif r['qualifying_evidence']:
            r['status']='EXCLUDE_PANEL_DIMENSION_PLUS';r['reasons'].insert(0,'User rule: any qualifying panel-dimension + excludes this file')
        elif r['ambiguous_evidence'] or r['reasons']:r['status']='REVIEW_REQUIRED'
        else:r['status']='NO_PANEL_DIMENSION_PLUS_DETECTED'
    except Exception as ex:
        r['reasons'].append(type(ex).__name__+': '+str(ex))
        r['coverage_complete']=False;r['status']='REVIEW_REQUIRED'
        # Even a positive followed by interruption must bind to unchanged source
        # bytes. Preserve exclusion only after a successful post-error hash check.
        if r['sha256'] is not None:
            try:
                r['hash_unchanged']=sha(p)==r['sha256']
                if not r['hash_unchanged']:r['reasons'].append('Source hash changed after interrupted scan')
                elif r['qualifying_evidence']:r['status']='EXCLUDE_PANEL_DIMENSION_PLUS'
            except Exception as hash_error:
                r['hash_unchanged']=None
                r['reasons'].append('Post-error hash verification failed: '+type(hash_error).__name__+': '+str(hash_error))
    return r

def controls():
    tests=[
      ('800W+700W*2350H*250D','panel_spec',False,'QUALIFYING'),
      ('40W*(50+50)H*15D','panel_spec',False,'QUALIFYING'),
      ('W400+400*H500*D150','material_spec',True,'QUALIFYING'),
      ('W(56+40)cmxH45cmxD10cm','material_spec',True,'QUALIFYING'),
      ('配電箱W:500+700','material_name',True,'QUALIFYING'),
      ('450W*560+240H*120D','panel_spec',False,'QUALIFYING'),
      ('700W*1100＋600H*450D*1.5t','material_spec',True,'QUALIFYING'),
      ('800+700*2350*250','panel_spec',False,'QUALIFYING'),
      ('NFB+1AUX','material_spec',False,'NONQUALIFYING'),
      ('FL+LS','material_spec',False,'NONQUALIFYING'),
      ('3C+1G','material_spec',False,'NONQUALIFYING'),
      ('銅排20+30','material_spec',False,'NONQUALIFYING'),
      ('材料+工資','material_spec',False,'NONQUALIFYING'),
      ('700W*1100H*450D','panel_spec',False,'NONE'),
      ('規格待定+另議','panel_spec',False,'AMBIGUOUS'),
      ('800+700*2350*250','material_spec',False,'AMBIGUOUS'),
      ('CASE+SS','material_name',True,'AMBIGUOUS'),
      ('NFB+1AUX','panel_spec',False,'NONQUALIFYING'),
      ('Cu bus+Support','material_spec',True,'NONQUALIFYING'),
      ('CASE:800W+700W*2350H*250D 含製作','material_spec',True,'QUALIFYING'),
      ('700W*1100+600H*450D*1.5t','material_spec',bool(ENCLOSURE.search('不繡鋼電控箱')),'QUALIFYING'),
      ('CASE:800W+700W*2350H*250D 含NFB','material_spec',True,'QUALIFYING'),
      ('CASE 800W*500H*200D NFB1+1','material_spec',True,'NONQUALIFYING'),
      ('NFB 1+1 Support','material_spec',True,'NONQUALIFYING'),
      ('800W+700W*2350H*250D 含NFB','material_spec',False,'AMBIGUOUS')]
    rows=[{'value':v,'role':role,'enclosure':enc,'expected':want,'actual':classify_plus(v,role,enc)} for v,role,enc,want in tests]
    assert all(x['expected']==x['actual'] for x in rows),rows
    assert SKIP_SHEET.search('原材料清單') and SKIP_SHEET.search('OK') and not SKIP_SHEET.search('未填')
    assert SKIP_FILE.search('工程(未填)(OK).xlsx') and not SKIP_FILE.search('工程(未填)+.xlsx')
    assert SKIP_FILE.search('工程未填OK.xlsx') and not SKIP_FILE.search('TOKYO未填.xlsx')
    from types import SimpleNamespace
    shifted=[SimpleNamespace(value=v) for v in ('說明',None,'材料名稱','規格','單位','數量','盤體名稱','盤體規格')]
    assert header_map(shifted)=={'material_name':2,'material_spec':3,'unit':4,'quantity':5,'panel_name':6,'panel_spec':7}
    assert header_map([SimpleNamespace(value=v) for v in ('說明','合約價格','日期')]) is None
    combined=[SimpleNamespace(value=v) for v in ('盤體名稱','盤體規格','材料名稱','規格+材料名稱','單位','數量')]
    assert header_map(combined)['material_spec']==3
    return {'status':'PASS','classification_controls':rows,'sheet_and_filename_boundary_controls':6,'shifted_and_unknown_schema_controls':3}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest',type=Path,help='JSON list of target paths or {cases:[{target_path:...}]}')
    group.add_argument('--discovery-dirs',nargs='+',type=Path)
    ap.add_argument('--priority-manifest',type=Path)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--seconds',type=float,default=300)
    a=ap.parse_args();out=a.output_dir
    if out.exists():raise SystemExit('Output directory must be fresh; preserving prior runs')
    out.mkdir(parents=True);(out/'CONTROLS.json').write_text(json.dumps(controls(),ensure_ascii=False,indent=2),encoding='utf-8')
    def loadmanifest(p):
        obj=json.loads(p.read_text(encoding='utf-8-sig'));obj=obj.get('cases',obj) if isinstance(obj,dict) else obj
        return [x if isinstance(x,str) else x.get('target_path',x.get('path')) for x in obj]
    if a.manifest:paths=loadmanifest(a.manifest);discovery={'manifest':str(a.manifest)}
    else:
        cmd=['rg','--files','--hidden','-g','*未填*','-g','!**/.git/**',*[str(p) for p in a.discovery_dirs]]
        run=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
        paths=run.stdout.splitlines();discovery={'command':cmd,'exit_code':run.returncode,'stderr':run.stderr}
    priority=loadmanifest(a.priority_manifest) if a.priority_manifest else []
    paths=list(dict.fromkeys(priority+paths));(out/'DISCOVERY.json').write_text(json.dumps({'paths':paths,'scope':discovery,'priority_manifest':str(a.priority_manifest)},ensure_ascii=False,indent=2),encoding='utf-8')
    start=time.monotonic();deadline=start+a.seconds;results=[]
    with (out/'inventory.jsonl').open('w',encoding='utf-8') as jf:
        for index,p in enumerate(paths):
            if time.monotonic()>deadline:
                r={'path':p,'sha256':None,'status':'UNSCANNED_FINITE_DEADLINE','reasons':['Finite scan deadline reached before file content access']}
            else:r=scan(p,deadline)
            results.append(r);jf.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');jf.flush()
            counts=dict(Counter(x['status'] for x in results))
            if (index+1)%10==0 or index+1==len(priority):
                checkpoint={'processed':len(results),'total':len(paths),'elapsed_seconds':round(time.monotonic()-start,3),'counts':counts,'priority_completed':index+1>=len(priority)}
                (out/'checkpoint.json').write_text(json.dumps(checkpoint,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(checkpoint),flush=True)
            if index+1==len(priority) and priority:
                (out/'PRIORITY_RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    (out/'inventory.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    with (out/'inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['path','sha256','status','project_id_path_metadata','reasons','qualifying_cell_count','ambiguous_cell_count']
        wr=csv.DictWriter(f,fields);wr.writeheader()
        for r in results:wr.writerow({k:(json.dumps(r.get('reasons',[]),ensure_ascii=False) if k=='reasons' else len(r.get('qualifying_evidence',[])) if k=='qualifying_cell_count' else len(r.get('ambiguous_evidence',[])) if k=='ambiguous_cell_count' else r.get(k)) for k in fields})
    summary={'scanner_version':VERSION,'scanner_sha256':sha(Path(__file__)),'completed':datetime.now().astimezone().isoformat(),'elapsed_seconds':round(time.monotonic()-start,3),'counts':dict(Counter(r['status'] for r in results)),'file_count':len(results),'rule':'Any 未填 with a + in the panel dimensions should be excluded, this is a sign of a misnamed 未填','limits':['File-level source screening only; project IDs are path metadata.','NO_PANEL_DIMENSION_PLUS_DETECTED is not gold validity.','Forbidden sheets are skipped before cell reads; unknown sheets/errors/missing caches require review.','No macros run, no links refreshed, no original written; no target values for generation.','Only dimension-plus evidence, small source-column contexts and nonqualifying plus observations retained.']}
    (out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
