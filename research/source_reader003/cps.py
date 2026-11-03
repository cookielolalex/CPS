"""CPS contract-only deterministic candidate engine. Importing performs no I/O.

This engine generates reviewable drafts, not semantic or production approval.
Only pinned sources explicitly listed in a caller-supplied manifest are read.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib
import io
import json
import math
import re
import sys
import zipfile
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET
import source_formats as formats

ENGINE = "CPS deterministic header-and-hierarchy parser 1.1.0-format-candidate-003; no LLM"
HEADERS = ['盤體名稱','盤體規格','材料名稱','規格','單位','數量','單價','複價','型號','廠牌','訂購廠商','工程編號','訂購客戶','使用客戶','需要日期','需要數量','合約價']
LETTERS = list('ABCDEFGHIJKLMNOPQ')
BAD = {'formula-error', 'missing-formula-cache', 'merged-covered', 'error'}
ALIASES = {
 'index': ['項次','項目編號','編號'],
 'description': ['項目及說明','工程項目','品名','品名規格','名稱','材料名稱','名稱·規範','說明','工料名稱','項目名稱','名稱及規格','項目'],
 'spec': ['規格','材料規格'], 'unit':['單位'], 'quantity':['數量','契約數量','合約數量'],
 'price':['單價','合約單價','契約單價'], 'remark':['備註','附註'],
 'model':['型號'], 'brand':['廠牌','品牌'], 'supplier':['訂購廠商','供應商']}

def compact(v): return re.sub(r'\s+', '', '' if v is None else str(v))
def stringify(v): return '' if v is None else str(v)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
    return h.hexdigest()
def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()
def safevalue(v):
    if isinstance(v, (dt.datetime, dt.date, dt.time)): return v.isoformat()
    if isinstance(v, float) and not math.isfinite(v): return None
    return v
def numeric(v):
    # Never coerce missing values, errors or commercial annotations to zero.
    if isinstance(v, bool) or v is None: return None
    if isinstance(v, (int,float)): return v if math.isfinite(v) else None
    t = str(v).strip()
    # Commas are valid only as complete thousands groups. Text numerals remain
    # exact source text: no float conversion, digit loss, or invented type.
    if not re.fullmatch(r'[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d+)', t): return None
    return v
def colname(i):
    out=''
    while i: i,k=divmod(i-1,26); out=chr(65+k)+out
    return out
def cellvalue(c): return None if c['state'] in BAD else c.get('cached') if c['state']=='cached-formula-value' else c.get('raw')
def reject_source(p):
    # An allowlist cannot accidentally authorize a historical or manufacturing file.
    text=unicodedata.normalize('NFKC',str(p)).casefold()
    forbidden=['未填','已填','板金','鈑金','電機','原材料清單','領料單','生產','製造','supplemental_research','quarantined','historical','holdout','benchmark_target']
    if any(x in text for x in forbidden) or re.search(r'(?i)(?<![a-z])ok(?![a-z])',text):
        raise ValueError('Forbidden generation source path: '+str(p))
    if p.suffix.lower() not in {'.xlsx','.xlsm','.xls','.ods'}: raise ValueError('Only original spreadsheet contract sources supported: '+str(p))
def canonical(p): return str(Path(p).resolve())
def assert_contract_sheet_names(names):
    for name in names:
        text=compact(unicodedata.normalize('NFKC',name)).casefold()
        if any(token in text for token in ['未填','已填','電機','板金','鈑金','原材料清單','領料單','生產','製造','supplemental_research']) or re.search(r'(?<![a-z])ok(?![a-z])',text):
            raise ValueError('Forbidden embedded non-contract sheet; entire workbook blocked before worksheet decoding: '+name)

def validate_manifest(manifest):
    if manifest.get('schema_version') != 1: raise ValueError('schema_version must be 1')
    allowed={canonical(p).casefold() for p in manifest.get('allowed_source_paths',[])}
    if not allowed: raise ValueError('Explicit allowed_source_paths is required')
    cases=manifest.get('contracts',[])
    ids=set()
    for case in cases:
        cid=case['case_id']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',cid) or cid in ids: raise ValueError('Unsafe or duplicate case_id')
        ids.add(cid)
        if case.get('scope_status','unverified') not in {'verified','partial','unverified'}: raise ValueError('Invalid scope_status')
        if not case.get('sources'): raise ValueError('No contract sources for '+cid)
        paths=set()
        for source in case['sources']:
            p=Path(source['path']).resolve(); reject_source(p)
            if str(p).casefold() not in allowed: raise ValueError('Source is not exact allowlisted: '+str(p))
            if source.get('role') not in {'contract','original_annex'}: raise ValueError('Unsupported source role')
            if not re.fullmatch(r'[0-9a-fA-F]{64}',source.get('sha256','')): raise ValueError('SHA256 required')
            if str(p).casefold() in paths: raise ValueError('Duplicate source')
            paths.add(str(p).casefold())
        for adopt in case.get('adopted_sheets',[]):
            if canonical(adopt['source_path']).casefold() not in paths: raise ValueError('Adoption points outside case sources')
            if adopt.get('authority') not in {'contract_detail','verified_annex'} or not adopt.get('basis'): raise ValueError('Adoption authority and basis required')
    if not cases: raise ValueError('No contracts')
    return True

def read_xlsx(source, _data=None):
    from openpyxl import load_workbook
    data=formats.source_bytes(source['path']) if _data is None else _data
    # Metadata guard runs before either workbook loader can decode sheet values.
    names=formats.xlsx_metadata(data,assert_contract_sheet_names)
    grid_metadata=formats.xlsx_grid_metadata(data,names)
    raw=load_workbook(io.BytesIO(data),data_only=False,keep_links=False); cached=load_workbook(io.BytesIO(data),data_only=True,keep_links=False)
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    sheets=[];total_cells=0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            native_sheets={}
            for meta in grid_metadata: native_sheets[meta['name']]=ET.fromstring(z.read(meta['member']))
            for s in raw:
                total_cells+=formats.grid_bound(s.max_row,s.max_column,'OOXML runtime')
                if total_cells>formats.MAX_CELLS: raise ValueError('OOXML runtime total cell limit')
                meta=next(m for m in grid_metadata if m['name']==s.title)
                if s.max_row>max(1,meta['rows']) or s.max_column>max(1,meta['columns']): raise ValueError('OOXML decoded extent exceeds preflight')
                covered={}; conflicts=[]; native={}
                for rg in s.merged_cells.ranges:
                    anchor=f'{colname(rg.min_col)}{rg.min_row}'
                    for rr in range(rg.min_row,rg.max_row+1):
                        for cc in range(rg.min_col,rg.max_col+1):
                            co=f'{colname(cc)}{rr}'
                            if co!=anchor: covered[co]=anchor
                for el in native_sheets[s.title].findall('.//m:sheetData/m:row/m:c',ns):
                    co=el.attrib['r']; f=el.find('m:f',ns); v=el.find('m:v',ns); it=el.find('m:is',ns)
                    native[co]={'type':el.get('t'),'formula':f.text if f is not None else None,'value':v.text if v is not None else None,'inline_text':''.join(it.itertext()) if it is not None else None}
                    if co in covered and (f is not None or (v is not None and v.text is not None) or it is not None): conflicts.append({'cell':co,'anchor':covered[co],'native':native[co]})
                rows=[]
                for rr in range(1,s.max_row+1):
                    cells=[]
                    for cc in range(1,s.max_column+1):
                        c=s.cell(rr,cc); cv=cached[s.title].cell(rr,cc); co=c.coordinate
                        state='merged-covered' if co in covered else 'formula-error' if c.data_type=='e' or cv.data_type=='e' else 'missing-formula-cache' if c.data_type=='f' and cv.value is None else 'cached-formula-value' if c.data_type=='f' else 'blank' if c.value is None else 'literal'
                        cells.append({'cell':co,'raw':safevalue(c.value),'cached':safevalue(cv.value),'state':state,'anchor':covered.get(co),'native':native.get(co)})
                    rows.append(cells)
                sheets.append({'name':s.title,'visibility':s.sheet_state,'dimensions':s.calculate_dimension(),'merges':[str(x) for x in s.merged_cells.ranges],'covered_conflicts':conflicts,'rows':rows})
            external=any(n.startswith('xl/externalLinks/externalLink') and n.endswith('.xml') for n in z.namelist())
        return {'sheets':sheets,'external_links_present':external,'grid_preflight':grid_metadata,'limitations':['Formulas copied only from saved caches; never recalculated.']}
    finally: raw.close(); cached.close()

def read_xls(source, dependency_dir=None, _data=None):
    try: xlrd=importlib.import_module('xlrd')
    except ImportError:
        if dependency_dir is None: raise RuntimeError('Legacy XLS requires xlrd; supply --dependency-dir')
        sys.path.insert(0,str(Path(dependency_dir).resolve()))
        try: xlrd=importlib.import_module('xlrd')
        finally: sys.path.pop(0)
    data=formats.source_bytes(source['path']) if _data is None else _data
    # CompDoc extracts only the OLE Workbook stream. Unlike open_workbook it
    # does not decode the shared-string table before all sheet names pass.
    from xlrd.compdoc import CompDoc
    container=CompDoc(data,logfile=io.StringIO())
    stream=container.get_named_stream('Workbook') or container.get_named_stream('Book')
    if stream is None: raise ValueError('No Workbook/Book OLE stream')
    entries=formats.biff8_sheet_metadata(stream,with_offsets=True)
    names=[entry['name'] for entry in entries]
    assert_contract_sheet_names(names)
    from xlrd.biffh import biff_rec_name_dict
    grid_metadata=formats.biff8_grid_metadata(stream,entries,set(biff_rec_name_dict))
    book=xlrd.open_workbook(file_contents=data,formatting_info=True,on_demand=True)
    sheets=[];total_cells=0
    try:
        if names!=book.sheet_names(): raise ValueError('BIFF metadata mismatch')
        for s in book.sheets():
            total_cells+=formats.grid_bound(s.nrows,s.ncols,'BIFF runtime')
            if total_cells>formats.MAX_CELLS: raise ValueError('BIFF runtime total cell limit')
            meta=next(m for m in grid_metadata if m['name']==s.name)
            if s.nrows>meta['rows'] or s.ncols>meta['columns']: raise ValueError('BIFF decoded extent exceeds preflight')
            covered={}; conflicts=[]
            for rlo,rhi,clo,chi in s.merged_cells:
                anchor=f'{colname(clo+1)}{rlo+1}'
                for rr in range(rlo,rhi):
                    for cc in range(clo,chi):
                        if (rr,cc)!=(rlo,clo): covered[(rr,cc)]=anchor
            rows=[]
            for rr in range(s.nrows):
                cells=[]
                for cc in range(s.ncols):
                    c=s.cell(rr,cc); co=f'{colname(cc+1)}{rr+1}'; value=safevalue(c.value)
                    state='merged-covered' if (rr,cc) in covered else 'error' if c.ctype==xlrd.XL_CELL_ERROR else 'blank' if c.ctype in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK) else 'literal-or-cache-unverified'
                    if c.ctype==xlrd.XL_CELL_ERROR: value=xlrd.error_text_from_code.get(c.value,str(c.value))
                    if state=='merged-covered' and c.ctype not in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK): conflicts.append({'cell':co,'anchor':covered[(rr,cc)],'raw':value})
                    cells.append({'cell':co,'raw':value,'cached':None,'state':state,'anchor':covered.get((rr,cc)),'xls_type':c.ctype})
                rows.append(cells)
            sheets.append({'name':s.name,'visibility':str(getattr(s,'visibility','unknown')),'dimensions':f'A1:{colname(s.ncols)}{s.nrows}','merges':list(s.merged_cells),'covered_conflicts':conflicts,'rows':rows})
        return {'sheets':sheets,'external_links_present':'unverified','grid_preflight':grid_metadata,'limitations':['Legacy XLS values may be literals or saved caches; xlrd does not expose formula text or verify external links.', 'Four documented non-materializing BIFF metadata types are bounded and hash-recorded without interpreting their UI text or application-cache payloads.']}
    finally: book.release_resources()

def read_source(source,dependency_dir=None):
    path=Path(source['path']).resolve(); reject_source(path)
    data=formats.source_bytes(path)
    actual=hashlib.sha256(data).hexdigest()
    if actual.lower()!=source['sha256'].lower(): raise ValueError('Source hash mismatch: '+str(path))
    container=formats.detect_container(data)
    if container=='BIFF8_OLE': book=read_xls(source,dependency_dir,_data=data)
    elif container=='OOXML_ZIP': book=read_xlsx(source,_data=data)
    elif container=='ODS_ZIP': book=formats.read_ods(data,assert_contract_sheet_names)
    else: raise ValueError('Unsupported actual source container')
    if sha(path)!=actual: raise ValueError('Source changed while reading: '+str(path))
    book.update({'path':str(path),'sha256':actual,'bytes':len(data),'role':source['role'],'detected_container':container,'source_extension':path.suffix.lower(),'metadata_guard_before_cell_decoding':True})
    return book

def header_mapping(row):
    values=[compact(cellvalue(c)) for c in row]; mapping={}
    for key,labels in ALIASES.items():
        for i,v in enumerate(values):
            if v in labels: mapping[key]=i; break
    if '項目' in values and any(v in ALIASES['description'] and v!='項目' for v in values):
        mapping['index']=values.index('項目')
        mapping['description']=next(i for i,v in enumerate(values) if v in ALIASES['description'] and v!='項目')
    # A visible 工程項目 heading merged across its index/name pair followed
    # by a separate 說明 column is a known structural header, not a license
    # to use fixed columns on unrelated layouts.
    for i,v in enumerate(values[:-2]):
        if v=='工程項目' and row[i+1].get('state')=='merged-covered' and row[i+1].get('anchor')==row[i]['cell'] and values[i+2]=='說明':
            mapping.update(index=i,description=i+1,spec=i+2)
    return mapping

def detect_header(row,nextrow=None):
    mapping=header_mapping(row)
    if all(x in mapping for x in ['description','unit','quantity']): return mapping,1
    # Two-row headers use actual labeled columns, never fixed positions.
    if nextrow is not None:
        nmap=header_mapping(nextrow)
        # A complete next-row header belongs to that row; do not let a
        # preamble/blank row reinterpret it as a two-line composite.
        if all(x in nmap for x in ['description','unit','quantity']): return None,0
        for key,i in nmap.items(): mapping.setdefault(key,i)
        if all(x in mapping for x in ['description','unit','quantity']): return mapping,2
    return None,0

def index_child(idx,parent):
    if not idx or not parent: return False
    # Dot, hyphen and parenthesized compound numbering only; never infer a
    # relationship from numeric magnitude or a nearest preceding heading.
    return any(idx.startswith(parent+d) for d in ['.','-','．','、','(' ,'（'])
def panel_title(text): return bool(re.search(r'配電盤|控制盤|儀表盤|電表箱|儀表箱|開關箱|控制箱|PANEL',text,re.I))
def provenance(c,book,sheet,rule='copy original visible value'):
    co=c['cell']; hit=re.search(r'\d+$',co)
    return {'source_path':book['path'],'source_sha256':book['sha256'],'sheet':sheet,'cell':co,'row':int(hit.group()) if hit else None,'raw':c.get('raw'),'cached':c.get('cached'),'state':c['state'],'rule':rule}

def parse_sheet(book,sheet,adoption,case):
    """Pure transformation over source snapshots; synthetic fixtures use this API."""
    assert_contract_sheet_names([sheet['name']])
    records=[]; out=[]; groups=[]; mapping=None; group=None; last=None; skip=0; unresolved=[]
    role='adopted_detail' if adoption else 'content_candidate_scope_unverified'
    result={'name':sheet['name'],'source_path':book['path'],'visibility':sheet['visibility'],'dimensions':sheet['dimensions'],'merges':sheet['merges'],'covered_conflicts':sheet['covered_conflicts'],'adoption':adoption,'role':role,'row_dispositions':records,'groups':groups,'review_reasons':unresolved}
    for key in ['stored_grid','row_visibility','column_visibility','row_storage_ranges','column_storage_ranges','compressed_blank_ranges']:
        if key in sheet: result[key]=sheet[key]
    # Analysis/resource tables never become materials simply through adoption.
    content=' '.join(stringify(cellvalue(c)) for r in sheet['rows'][:20] for c in r)
    analysis=('單價分析' in sheet['name'] or '工料名稱' in content)
    resource=('資源統計' in sheet['name'] or '資源統計表' in content)
    candidate_headers=any(detect_header(r,sheet['rows'][i+1] if i+1<len(sheet['rows']) else None)[0] for i,r in enumerate(sheet['rows']))
    review_only=case.get('generation_mode')=='review_only' or case.get('block_material_generation') is True
    eligible=candidate_headers and not analysis and not resource and not review_only
    if analysis or resource: unresolved.append('Analysis/resource table requires separately proven main-item/basis linkage; no automatic expansion or adoption.')
    if not adoption: unresolved.append('No verified sheet adoption; sheet name alone supplies no contract authority.')
    if review_only: unresolved.append('Manifest explicitly restricts this source scope to review-only; no candidate material rows.')
    if not candidate_headers: unresolved.append('No supported material-table headers detected.')
    if sheet['visibility'] not in {'visible','0'}: unresolved.append('Hidden sheet authority/version requires independent confirmation.')
    for ri,row in enumerate(sheet['rows'],1):
        values=[cellvalue(c) for c in row]
        d={'row':ri,'raw_cells':row,'visible_values':values,'kind':'blank' if not any(v is not None and stringify(v)!='' for v in values) else 'review_only','output_ids':[]}; records.append(d)
        issues=[{'cell':c['cell'],'state':c['state'],'raw':c.get('raw'),'cached':c.get('cached')} for c in row if c['state'] in {'formula-error','missing-formula-cache','error'}]
        if issues: d['source_issues']=issues
        if issues and d['kind']=='blank': d['kind']='source_error_review'
        if not eligible: continue
        if skip: d['kind']='header_continuation'; skip-=1; continue
        h,consumed=detect_header(row,sheet['rows'][ri] if ri<len(sheet['rows']) else None)
        if h: mapping=h;skip=consumed-1;d['kind']='header';last=None;continue
        if not any(v is not None and stringify(v)!='' for v in values) and not issues: last=None;continue
        if mapping is None: d['kind']='preamble';continue
        def get(k):
            ix=mapping.get(k)
            return row[ix] if ix is not None and ix<len(row) else {'cell':f'?{ri}','raw':None,'cached':None,'state':'blank'}
        desc=stringify(cellvalue(get('description')));spec=stringify(cellvalue(get('spec')));remark=stringify(cellvalue(get('remark')))
        idx=compact(cellvalue(get('index'))); unit=cellvalue(get('unit')); qty=cellvalue(get('quantity'))
        markers=[{'value':stringify(v),'cell':c['cell']} for c,v in zip(row,values) if any(t in stringify(v) for t in ['不含估價','供料','自運','原數量'])]
        if compact(desc) in {'合計','小計','總計','總價','計','營業稅','稅額'}:
            d['kind']='total';last=None;group=None;continue
        if re.search(r'第\s*\d+\s*頁|PAGE\s*[:：]',desc,re.I): d['kind']='page_metadata';last=None;continue
        # End ancestry on a proven sibling or new numbered section.
        if group and idx and not index_child(idx,group['index']): group=None
        hasqty=qty is not None and compact(qty)!=''; hasunit=unit is not None and compact(unit)!=''
        critical=[k for k in ['description','unit','quantity'] if get(k)['state'] in {'formula-error','missing-formula-cache','error'}]
        if critical:
            d.update(kind='blocked_key_fields',review_reasons=['Unusable source field: '+k for k in critical]);unresolved.append(f'Row {ri}: unusable key cells');last=None;continue
        if idx and not hasqty and re.search(r'工程|材料費|施工費|費用|儀表$',desc) and not panel_title(desc):
            d['kind']='section_with_unit_not_material';last=None;group=None;continue
        # A panel header is admitted only with explicit index ancestry and later descendants.
        future_child=bool(idx) and any(index_child(compact(cellvalue(r[mapping['index']])) if 'index' in mapping and mapping['index']<len(r) else '',idx) for r in sheet['rows'][ri:])
        if panel_title(desc) and idx and future_child:
            group={'id':f'{sheet["name"]}:{ri}','index':idx,'title':desc,'title_provenance':[provenance(get('description'),book,sheet['name'])],'spec':spec or None,'spec_provenance':[provenance(get('spec'),book,sheet['name'])] if spec else [],'relationship':'explicit_contract_numbered_group','physical_inside':'unproven','allocation':'unresolved; no box-count multiplication'}
            groups.append(group);d['kind']='panel_group';last=None;continue
        if not hasunit and not hasqty and not idx:
            if group and last is None and (desc or spec):
                # Adjacent title continuation only; explicit fragments remain separate evidence.
                if records[-2]['kind'] in {'panel_group','panel_title_continuation'}:
                    group['title']+='\n'+desc;group['title_provenance'].append(provenance(get('description'),book,sheet['name'],'newline-separated adjacent title continuation; no numeric token fusion'))
                    if spec: group['spec']='\n'.join(x for x in [group['spec'],spec] if x);group['spec_provenance'].append(provenance(get('spec'),book,sheet['name']))
                    d['kind']='panel_title_continuation';continue
            continuation_roles=any(get(k)['state'] not in {'blank','merged-covered'} for k in ['model','brand','supplier','price'])
            if last and (desc or spec or remark or markers or issues or continuation_roles):
                if panel_title(desc) or re.search(r'設備工程|材料費|施工費|工程名稱|施工地點',desc):
                    d['kind']='ambiguous_heading';d['review_reasons']=['Heading-like text cannot be safely joined to preceding material.'];unresolved.append(f'Row {ri}: ambiguous heading');last=None;group=None;continue
                d['kind']='continuation';d['output_ids']=[last['id']];last['source_rows'].append(ri)
                if desc:
                    last['values'][2]+='\n'+desc
                    last['field_provenance']['C']['sources'].append(provenance(get('description'),book,sheet['name'],'newline-separated adjacent unnumbered description; no numeric token fusion'))
                for key in ['spec','remark']:
                    v=stringify(cellvalue(get(key)))
                    if v:
                        last['description_streams'][key].append(v)
                        last['field_provenance']['D'].setdefault('sources',[]).append(dict(provenance(get(key),book,sheet['name'],'newline-separated source fragment'),stream=key))
                last['values'][3]='\n'.join(last['description_streams']['spec']+last['description_streams']['remark']) or None
                last['commercial_markers'].extend(markers)
                if markers: last['review_reasons'].append('Continuation commercial markers retained without deletion or zero-price inference.')
                # Every explicit continuation role is preserved, even when it
                # cannot safely replace an existing field or establish Q.
                for letter,key in [('I','model'),('J','brand'),('K','supplier'),('Q','price')]:
                    c=get(key);value=cellvalue(c)
                    if key not in mapping or c['state']=='blank': continue
                    evidence=provenance(c,book,sheet['name'],'explicit continuation role; no conflicting overwrite')
                    if c['state'] in BAD or (letter=='Q' and (not adoption or numeric(value) is None)):
                        last.setdefault('continuation_anomalies',[]).append({'field':letter,'source':evidence,'reason':'Unusable value or contract-price role not independently reviewed.'})
                        last['status']='partial';continue
                    current=last['values'][LETTERS.index(letter)]
                    if current is None:
                        last['values'][LETTERS.index(letter)]=value
                        last['field_provenance'][letter]={'sources':[evidence]}
                    elif current==value:
                        last['field_provenance'][letter].setdefault('sources',[]).append(evidence)
                    else:
                        last.setdefault('continuation_anomalies',[]).append({'field':letter,'source':evidence,'existing_value':current,'reason':'Conflicting explicit continuation value retained for review; existing value not overwritten.'})
                        last['status']='partial'
                for key in ['spec','remark']:
                    c=get(key)
                    if c['state'] in {'formula-error','missing-formula-cache','error'}:
                        last.setdefault('continuation_anomalies',[]).append({'field':'D','source':provenance(c,book,sheet['name']),'reason':'Unusable continuation specification/remark.'});last['status']='partial'
                if last.get('continuation_anomalies'):
                    last['release_state']='PARTIAL_REVIEW_REQUIRED';last['review_reasons'].append('Continuation conflicts/unusable cells require review; see continuation_anomalies.')
                last['review_reasons'].append('Unnumbered continuation requires semantic confirmation.');continue
        if not desc or (not hasunit and not hasqty):
            d['kind']='unresolved_section_or_row';d['review_reasons']=['No supported material/service structure.'];unresolved.append(f'Row {ri}: unresolved content');last=None;group=None;continue
        vals=[None]*17;pr={k:{'state':'not_supplied','reason':'No explicit authorized source role for this field.'} for k in LETTERS}
        reasons=['Contract scope/material-versus-service classification requires independent semantic review.','Quantity basis unresolved; original quantity copied without multiplication.']
        ident=f'{case["case_id"]}:{book["sha256"][:12]}:{sheet["name"]}:{ri}'
        def assign(letter,key,value=None):
            c=get(key);value=cellvalue(c) if value is None else value
            if c['state'] in BAD: reasons.append(f'{letter}: source cell unusable ({c["state"]})');return
            vals[LETTERS.index(letter)]=value;pr[letter]={'sources':[provenance(c,book,sheet['name'])]}
        assign('C','description',desc);assign('E','unit');assign('F','quantity')
        fragments=[(k,stringify(cellvalue(get(k)))) for k in ['spec','remark'] if cellvalue(get(k)) is not None and stringify(cellvalue(get(k)))!='']
        if fragments: vals[3]='\n'.join(v for k,v in fragments);pr['D']={'sources':[dict(provenance(get(k),book,sheet['name'],'preserve separate complete specification/remark streams; newline separator'),stream=k) for k,v in fragments]}
        if group and index_child(idx,group['index']):
            vals[0]=group['title'];vals[1]=group['spec'];pr['A']={'sources':group['title_provenance'],'relationship':group['relationship'],'group_id':group['id'],'physical_inside':'unproven','allocation':group['allocation']};pr['B']={'sources':group['spec_provenance']}
        else: reasons.append('Panel relationship not proven; A/B blank.')
        for letter,key in [('I','model'),('J','brand'),('K','supplier')]:
            if key in mapping and cellvalue(get(key)) is not None: assign(letter,key)
        pc=get('price');pv=numeric(cellvalue(pc))
        if adoption and 'price' in mapping and pv is not None and pc['state'] not in BAD:
            assign('Q','price',pv);pr['Q']['semantics']='contract unit price from explicitly adopted detail header; not procurement price'
        elif 'price' in mapping and cellvalue(pc) is not None: reasons.append('Q unavailable or commercial annotation; no price inferred.')
        identity=case.get('internal_project_id')
        if identity and identity.get('basis'):
            vals[11]=identity['value'];pr['L']={'value':identity['value'],'namespace':'internal project identifier','basis':identity['basis']}
        pr['G']=pr['H']={'state':'stage_blank','reason':'Procurement unit/extended prices are not generated from contract prices.'}
        if markers: reasons.append('Commercial markers retained; no item deletion or zero-price inference.')
        status='partial' if not adoption or case.get('scope_status')!='verified' or not hasqty or numeric(qty) is None or any(c['state'] in BAD for c in [get('spec'),get('remark'),get('price')]) else 'supported'
        if status=='partial': reasons.append('Missing, nonnumeric or unusable quantity/specification/price evidence.')
        item={'id':ident,'values':vals,'field_provenance':pr,'source_rows':[ri],'source_sheet':sheet['name'],'source_path':book['path'],'status':status,'release_state':'PARTIAL_REVIEW_REQUIRED' if status=='partial' else 'DRAFT_REVIEW_REQUIRED','review_required':True,'semantic_status':'pending_independent_review','review_reasons':reasons,'commercial_markers':markers,'quantity_basis':'original_source_unresolved','group_id':group['id'] if vals[0] else None,'description_streams':{key:[v for k,v in fragments if k==key] for key in ['spec','remark']}}
        out.append(item);d['kind']='output_draft';d['output_ids']=[ident];last=item
    return result,out

def generate_contract(case,manifest,dependency_dir=None):
    validate_manifest(dict(manifest,contracts=[case]))
    result={'schema_version':1,'schema_columns':17,'case_id':case['case_id'],'code':case['case_id'],'split':case.get('split'),'engine':ENGINE,'headers':HEADERS,'scope_status':case.get('scope_status','unverified'),'scope_reason':case.get('scope_reason'),'status':'blocked','deployment_status':'NOT_APPROVED','semantic_acceptance':'PENDING_INDEPENDENT_SOURCE_REVIEW','rows':[],'sheets':[],'sources':[],'review_reasons':[],'access_log':[],'analysis_blocks':[]}
    for source in case['sources']:
        try: book=read_source(source,dependency_dir)
        except Exception as exc:
            result['review_reasons'].append(type(exc).__name__+': '+str(exc));result['sources'].append({'path':source['path'],'status':'blocked','reason':str(exc)});continue
        result['access_log'].append({'path':book['path'],'sha256':book['sha256'],'operation':'hash and read original contract workbook only'})
        result['sources'].append({k:v for k,v in book.items() if k!='sheets'})
        if book['external_links_present'] is not False: result['review_reasons'].append('External links present or unverified; no updates performed.')
        for sheet in book['sheets']:
            matches=[a for a in case.get('adopted_sheets',[]) if canonical(a['source_path']).casefold()==book['path'].casefold() and a['sheet']==sheet['name']]
            if len(matches)>1: raise ValueError('Duplicate adoption for sheet')
            sr,rows=parse_sheet(book,sheet,matches[0] if matches else None,case)
            result['sheets'].append(sr);result['rows'].extend(rows)
            if 'Analysis/resource' in ' '.join(sr['review_reasons']):
                result['analysis_blocks'].append({'source_path':book['path'],'source_sha256':book['sha256'],'sheet':sheet['name'],'status':'staged_review_only_not_material_rows','reason':'Main-item, scope, denominator and expansion authority unproven.','source_row_range':[1,len(sheet['rows'])]})
    if result['rows']:
        unresolved=any(s['review_reasons'] or s['covered_conflicts'] for s in result['sheets'])
        result['status']='partial' if unresolved or result['review_reasons'] or case.get('scope_status')!='verified' or any(r['status']=='partial' for r in result['rows']) else 'supported'
    else: result['review_reasons'].append('No supported adopted contract rows; source-only review package preserved.')
    if case.get('scope_status')=='unverified':
        result['review_reasons'].append('Contract adoption/version/scope unverified; diagnostic candidate rows cannot be released.')
        result['unattended_release']='blocked'
    if case.get('generation_mode')=='review_only' or case.get('block_material_generation') is True: result['status']='blocked'
    result['counts']={'generated_rows':len(result['rows']),'source_rows':sum(len(s['row_dispositions']) for s in result['sheets']),'classified_rows':sum(len(s['row_dispositions']) for s in result['sheets']),'blocked_rows':sum(d['kind']=='blocked_key_fields' for s in result['sheets'] for d in s['row_dispositions'])}
    if result['counts']['blocked_rows'] and result['rows']: result['status']='partial'
    result['coverage_complete']=result['counts']['source_rows']==result['counts']['classified_rows'] and len(result['access_log'])==len(case['sources'])
    result['coverage_meaning']='All materialized source-grid rows have a disposition; ODS proven-empty trailing repeats are separately retained in compressed_blank_ranges with original coordinates and attributes. Semantic correctness/completeness is not established.'
    return result

def write_json(p,value): Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding='utf-8')
def batch_generate(manifest,output_dir,dependency_dir=None):
    validate_manifest(manifest)
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    # Existing results are immutable. A fresh output directory is required.
    if any(out.iterdir()): raise ValueError('Output directory must be empty; refusing to overwrite a run')
    summaries=[]
    for case in manifest['contracts']:
        result=generate_contract(case,manifest,dependency_dir);p=out/(case['case_id']+'.json');write_json(p,result)
        summaries.append({'case_id':case['case_id'],'status':result['status'],'counts':result['counts'],'output':str(p),'sha256':sha(p)})
    receipt={'engine':ENGINE,'generated_utc':utc(),'input_manifest_sha256':hashlib.sha256(json.dumps(manifest,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'runtime_sha256':sha(__file__),'runtime_dependencies':{'source_formats.py':sha(formats.__file__)},'outputs':summaries,'targets_read':False,'historical_comparison':'NOT_PERFORMED','deployment':'NOT_APPROVED'}
    write_json(out/'BATCH_RECEIPT.json',receipt)
    return receipt

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ['validate-manifest','generate']:
        p=sub.add_parser(command);p.add_argument('--manifest',required=True)
        if command=='generate': p.add_argument('--output-dir',required=True);p.add_argument('--dependency-dir')
    args=parser.parse_args(argv);manifest=json.loads(Path(args.manifest).read_text(encoding='utf-8-sig'))
    if args.command=='validate-manifest': validate_manifest(manifest);print('Manifest structure and generation-path policy valid; no source files read.')
    else: print(json.dumps(batch_generate(manifest,args.output_dir,args.dependency_dir),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
