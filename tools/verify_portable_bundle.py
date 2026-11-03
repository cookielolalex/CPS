"""Offline, read-only CPS handoff checks. No model, workbook authoring or original paths."""
import argparse, hashlib, importlib.util, json, os, sys, zipfile
from pathlib import Path

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(b): return hashlib.sha256(b).hexdigest()
def within(root, rel):
    p=(root/rel).resolve()
    if not p.is_relative_to(root): raise ValueError('BUNDLE_PATH_ESCAPE')
    return p

def pinned(root, pin):
    p=within(root,pin['bundle_path']); b=p.read_bytes()
    if digest(b)!=pin['sha256'] or len(b)!=pin['bytes']: raise ValueError('PIN_MISMATCH:'+pin['bundle_path'])
    return p,b

def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def letters(n):
    s='';n+=1
    while n:n,k=divmod(n-1,26);s=chr(65+k)+s
    return s

def read_legacy(root, config, cid):
    case=config['cases'][cid];source,data=pinned(root,case['original'])
    helper,_=pinned(root,config['legacy_helper'])
    for pin in config['xlrd_members']:pinned(root,pin)
    dep=within(root,'private/deps');sys.path.insert(0,str(dep))
    import xlrd
    assert xlrd.__version__=='2.0.2' and Path(xlrd.__file__).resolve()==dep/'xlrd/__init__.py'
    # Rebind dependency lookup only. The frozen BIFF decoder/cache checks are unchanged.
    reader=module(helper,'cps_archived_biff_reader');reader.load_xlrd=lambda:xlrd
    book,formulas,fmt=reader.parse_legacy(data)
    sheets=[]
    for i,s in enumerate(book.sheets()):
        f={(r,c) for r,c,_ in formulas[i]}
        rows=[]
        for r in range(s.nrows):
            cells=[]
            for c in range(s.ncols):
                typ=s.cell_type(r,c)
                cells.append(dict(cell=f'{letters(c)}{r+1}',saved_cell_type=typ,value=None if typ in (0,6) else s.cell_value(r,c),formula_record_present=(r,c) in f))
            rows.append(dict(row=r+1,cells=cells))
        sheets.append(dict(name=s.name,visibility=s.visibility,physical_rows=s.nrows,columns=s.ncols,merges=s.merged_cells,formula_records=len(f),rows=rows))
    book.release_resources()
    return dict(schema='cps.portable-source-observations.v1',case_id=cid,source=case['original'],source_adoption='unverified',
        role='source_only_reconstructed_saved_cache_observations_not_trial_admission',format=fmt,sheets=sheets)

def source_checks(root):
    config=load(root/'private/PORTABLE_SOURCE_INPUTS.json');out={}
    for cid in ('1140908','1141208'):
        case=config['cases'][cid];d=read_legacy(root,config,cid)
        cells={(s['name'],c['cell']):c for s in d['sheets'] for r in s['rows'] for c in r['cells']}
        if cid=='1140908':
            old=json.loads(pinned(root,case['comparison_snapshot'])[1]);assert old['sheet_names']==[s['name'] for s in d['sheets']]
            wanted={(r['sheet'],c['cell']):c for r in old['rows'] for c in r['cells']}
            assert len(wanted)==len(cells)==560
            for k,v in wanted.items():
                a=cells[k];assert a==v and type(a['value']) is type(v['value']),k
            compared=len(wanted)
        else:
            old=json.loads(pinned(root,case['comparison_snapshot'])[1]);assert [s['name'] for s in old['sheets']]==[s['name'] for s in d['sheets']]
            wanted={(s['name'],f"{letters(c['col']-1)}{c['row']}"):c for s in old['sheets'] for c in s['cells']}
            assert set(wanted)=={k for k,c in cells.items() if c['saved_cell_type'] not in (0,6)}
            for k,v in wanted.items():
                a=cells[k];assert a['saved_cell_type']==v['ctype'] and a['value']==v['value'] and type(a['value']) is type(v['value']),k
            assert len(cells)==376 and len(d['sheets'])==3
            prepared=json.loads(pinned(root,case['portable_inventory'])[1]);assert prepared==json.loads(json.dumps(d))
            compared=len(wanted)
        for p in case['views']:
            assert pinned(root,p)[1].startswith(b'\x89PNG\r\n\x1a\n')
        out[cid]=dict(worksheets=len(d['sheets']),positions=len(cells),nonempty=sum(x['value'] not in ('',None) for x in cells.values()),
            formula_records=sum(s['formula_records'] for s in d['sheets']),prior_snapshot_cells_reconciled=compared,pinned_views=len(case['views']))
    return out

def saved_cells(root, saved):
    sys.path.insert(0,str(within(root,'private/deps')))
    import openpyxl
    assert Path(openpyxl.__file__).resolve().is_relative_to(within(root,'private/deps/openpyxl'))
    workbook,_=pinned(root,saved['workbook']);matrix=json.loads(pinned(root,saved['matrix'])[1])['sheets']
    w=openpyxl.load_workbook(workbook,read_only=True,data_only=False,keep_links=False);count=0
    try:
        assert w.sheetnames==[s['name'] for s in matrix]
        for s in matrix:
            ws=w[s['name']];rows=s['values'];cols=max(map(len,rows))
            for i,row in enumerate(ws.iter_rows(min_row=1,max_row=max(ws.max_row or 0,len(rows)),max_col=max(ws.max_column or 0,cols))):
                for j,cell in enumerate(row):
                    assert cell.data_type!='f'
                    expected=rows[i][j] if i<len(rows) and j<len(rows[i]) else None
                    assert cell.value==expected and (type(cell.value)==type(expected) or type(cell.value) in (int,float) and type(expected) in (int,float)),(s['name'],i+1,j+1)
                    count+=int(i<len(rows) and j<len(rows[i]))
    finally:w.close()
    return count

def evaluation_checks(root):
    cfg=load(root/'private/PORTABLE_EVALUATION_INPUTS.json')
    comparer,_=pinned(root,cfg['comparer']);m=module(comparer,'cps_archived_comparer')
    gold=json.loads(pinned(root,cfg['expectations'])[1]);out={}
    for letter,v in cfg['readers'].items():
        c=json.loads(pinned(root,v['carrier'])[1]);prior=json.loads(pinned(root,v['comparison'])[1]);prior.pop('bindings')
        actual=m.evaluate(gold,c)
        assert actual==prior,'SAVED_EVALUATION_REPLAY_MISMATCH:'+letter
        core=actual['metrics']['overall']['modes']['canonical']['core']
        out[letter]=dict(core_matches=core['matches'],core_denominator=core['denominator'],saved_comparison_exact=True,
            saved_workbook_cells_verified=saved_cells(root,v),new_model_generation=False)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True,type=Path);p.add_argument('--phase',required=True,choices=['source','evaluation']);a=p.parse_args()
    root=a.bundle.resolve(strict=True);runtime=Path(sys.base_prefix).resolve();sys.dont_write_bytecode=True
    blocked=[];reads=set()
    def guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve();mode=args[1];flags=args[2]
            if isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise PermissionError('READ_ONLY_VERIFICATION')
            if not(path.is_relative_to(root) or path.is_relative_to(runtime)):
                blocked.append(str(path));raise PermissionError('OUTSIDE_EXTRACTED_BUNDLE')
            if path.is_relative_to(root):
                rel=path.relative_to(root).as_posix();reads.add(rel)
                if a.phase=='source' and ('/evaluation_only/' in rel or rel.startswith(('private/naming_study/','private/comparisons/','private/refinement/source_expectations','private/refinement/source_evaluation','private/refinement/integration','private/PORTABLE_EVALUATION'))):
                    raise PermissionError('SOURCE_PHASE_EVALUATION_FILE_FORBIDDEN')
        elif event in ('subprocess.Popen','os.system','socket.connect','socket.getaddrinfo','os.startfile'):
            raise PermissionError('OFFLINE_VERIFICATION_ONLY')
    sys.addaudithook(guard)
    # Prove that a forbidden original root is denied before any OS file open.
    probe=Path(r'D:\Data Center\cps_portability_guard_probe') if os.name=='nt' else Path('/Data Center/cps_portability_guard_probe')
    try:probe.open('rb');raise AssertionError('GUARD_DID_NOT_DENY')
    except PermissionError as exc:assert str(exc)=='OUTSIDE_EXTRACTED_BUNDLE'
    result=source_checks(root) if a.phase=='source' else evaluation_checks(root)
    assert len(blocked)==1,'UNEXPECTED_EXTERNAL_OPEN_ATTEMPT'
    print(json.dumps(dict(status='PASS',phase=a.phase,result=result,bundle_files_read=len(reads),intentional_original_root_denials=1,
      unexpected_external_file_opens=0,python=sys.version.split()[0],new_model_calls=0,scope='Python file-open guard, not OS-level sandbox; no external project data reads.'),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
