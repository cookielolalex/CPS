"""Search only pinned development source-profile outputs; no target files opened."""
import hashlib,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path('D:/STMS Price Quote/runs/CONTRACT-WEITIAN-20261030-001/cps_refinement_001/baseline_eval_002')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
freeze=read(BASE/'BASELINE_FREEZE.json');cohorts=read(BASE/'COHORTS.json')
allowed={c['case_id']:c for c in cohorts['cases']}
reserved=set(cohorts['reserved_case_ids']);assert not set(allowed)&reserved
excluded={'1110106','1110201','1110909','1111101','1121102','1130309','1130906'}
assert not set(allowed)&excluded
nouns=re.compile(r'斷路器|熔絲開關|接觸器|電磁開關|繼電器|電驛|端子台|模組|變壓器|電表|傳訊器|感測器|指示燈|按鈕|選擇開關|保險絲|供應器|控制器|切換開關|互感器|比流器|避雷器|突波保護器|電纜|電線|箱體|配電盤|管件|閥')
code=re.compile(r'[A-Za-z][A-Za-z0-9]*(?:[-_/][A-Za-z0-9.]+)+|[A-Za-z]{1,8}\d[A-Za-z0-9.-]*')
lead=re.compile(r'^\s*([A-Za-z][A-Za-z0-9./_+ -]{0,40}|[0-9][A-Za-z0-9./_+ *×"-]{0,35})')
hits=[];pins=[];rows=0
for f in freeze['files']:
    if not f.get('generation_eligible'):continue
    cid=f['case_id'];assert cid in allowed and cid not in reserved and cid not in excluded
    p=Path(f['path']);raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest();assert h==f['sha256']
    x=json.loads(raw);pins.append(dict(path=str(p),sha256=h,bytes=len(raw),case_id=cid));rows+=len(x.get('rows',[]))
    for r in x.get('rows',[]):
        vals=r['values'];c=str(vals[2] or '');d=str(vals[3] or '');k=[]
        m=nouns.search(c);prefix=c[:m.start()] if m else ''
        if m and code.search(prefix):k.append('code_like_before_name_candidate')
        if m and lead.match(c) and prefix.strip():k.append('latin_or_numeric_prefix_before_name_candidate')
        if c and not nouns.search(c) and nouns.search(d) and (code.search(c) or re.fullmatch(r'[A-Za-z0-9 ._()/+-]{2,40}',c)):k.append('name_in_spec_after_code_like_description_candidate')
        if re.search(r'型號\s*[:：]',c+d):k.append('explicit_model_label_candidate')
        if k:hits.append(dict(case_id=cid,cohort=allowed[cid]['cohort'],id=r['id'],C=c,D=d,I=vals[8],J=vals[9],categories=k,
            C_sources=r.get('field_provenance',{}).get('C'),D_sources=r.get('field_provenance',{}).get('D')))
summary=dict(files=len(pins),generated_rows_scanned=rows,candidate_rows=len(hits),
    by_category={k:sum(k in h['categories'] for h in hits) for k in sorted({k for h in hits for k in h['categories']})},
    target_reads=0,reserved_case_reads=0,original_contract_reads=0,
    warning='Pattern discovery in prior source-only snapshots, not model execution, accepted naming rules or full material completeness. Candidates need source-role review.')
for name,obj in [('BROAD_SOURCE_CANDIDATES.json',hits),('BROAD_SOURCE_PINS.json',pins),('BROAD_SOURCE_SUMMARY.json',summary)]:
    (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
