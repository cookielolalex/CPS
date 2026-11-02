"""Source-only comparator. Exact schema/source expectations must be frozen before use.
No fuzzy strings, recalculation, target reading, row deletion or post-output alternatives.
Semantic nonitem/provenance audit is deliberately separate and remains a mandatory gate.
"""
import argparse, datetime, hashlib, json, re, unicodedata
from pathlib import Path

COLS='ABCDEFGHIJKLMNOPQ'; RAW=('description','unit','quantity','unit_price','amount','remarks')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def norm(x): return re.sub(r'\s+',' ',unicodedata.normalize('NFC',x)).strip() if isinstance(x,str) else x
def same(a,b,normalized=False):
    # bool is not a number. JSON numeric int/float equivalent only for same finite value.
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return a==b
    return type(a) is type(b) and (norm(a)==norm(b) if normalized else a==b)
def count(n,d):return {'matches':n,'denominator':d,'percent':100*n/d if d else None}
def check_interface(expected,carrier):
    interface=expected['carrier_contract']
    for k in ['schema','case_id','family_id','source']:
        if carrier.get(k)!=interface[k]:raise ValueError('CARRIER_INTERFACE_MISMATCH:'+k)
def located(item):
    return item.get('location',{})
def corresponding(expected,items):
    result={};used=set();incidents=[]
    for e in expected:
        # Exact original worksheet and anchor, not name similarity or positional pairing.
        key=f'B{e["anchor_row"]}'
        hits=[(k,x) for k,x in enumerate(items) if located(x).get('sheet')==e['sheet'] and key in located(x).get('cells',[])]
        if len(hits)==1 and hits[0][0] not in used:
            k,x=hits[0];result[e['id']]=x;used.add(k)
        else:
            incidents.append({'expected_id':e['id'],'sheet':e['sheet'],'anchor':key,'match_count':len(hits),'status':'MISSING' if not hits else 'AMBIGUOUS_OR_DUPLICATED'})
    return result,[x for k,x in enumerate(items) if k not in used],incidents
def evaluate(expected,carrier):
    rr=expected['rows'];details=carrier.get('items',[]);components=carrier.get('components',[]);items=details+components
    if expected['denominators']['component_rows']!=0 or any(e['category']!='detail' for e in rr):raise ValueError('CASE043_EXPECTATIONS_REQUIRE_DETAIL_ONLY')
    detail_objects={id(x) for x in details};component_objects={id(x) for x in components}
    paired,extras,incidents=corresponding(rr,items)
    row_results=[]; role_defects=[]; link_results=[]
    for e in rr:
        a=paired.get(e['id']);av=a.get('values',[]) if a else []
        v=e['expected_values']; raw=a.get('raw',{}) if a else {}
        canonical={c:len(av)==17 and same(av[j],v[j]) for j,c in enumerate(COLS)}
        normalized={c:len(av)==17 and same(av[j],v[j],True) for j,c in enumerate(COLS)}
        declared=dict(canonical);declared_norm=dict(normalized);matched_alt=[];matched_alt_norm=[]
        for k,alt in enumerate(e.get('C_D_alternatives',[])):
            if len(av)==17 and same(av[2],alt['C']) and same(av[3],alt['D']):
                declared['C']=declared['D']=True;matched_alt.append(k)
            if len(av)==17 and same(av[2],alt['C'],True) and same(av[3],alt['D'],True):
                declared_norm['C']=declared_norm['D']=True;matched_alt_norm.append(k)
        raw_equal={k:a is not None and same(raw.get(k),e['raw'][k]) for k in RAW}
        raw_norm={k:a is not None and same(raw.get(k),e['raw'][k],True) for k in RAW}
        comp=a.get('composition') if a else None
        role_ok=a is not None and ((e['category']=='detail' and id(a) in detail_objects and 'composition' not in a) or (e['category']=='component' and id(a) in component_objects and isinstance(comp,dict)))
        if not role_ok:role_defects.append(e['id'])
        row_results.append({'id':e['id'],'category':e['category'],'generated_id':a.get('id') if a else None,'correspondence':a is not None,'role_pass':role_ok,'canonical':canonical,'normalized':normalized,'declared_alternatives':declared,'declared_alternatives_normalized':declared_norm,'matched_complete_tuple_alternatives':matched_alt,'matched_complete_tuple_alternatives_normalized':matched_alt_norm,'raw_literal':raw_equal,'raw_normalized':raw_norm,'unsupported_populated_columns':[c for j,c in enumerate(COLS) if len(av)==17 and v[j] is None and av[j] is not None],'field_differences':[{'column':c,'expected':v[j],'actual':av[j] if len(av)==17 else None} for j,c in enumerate(COLS) if not canonical[c]],'raw_differences':[{'field':k,'expected':e['raw'][k],'actual':raw.get(k)} for k in RAW if not raw_equal[k]]})
    metrics={}
    for cat in ['detail','component','overall']:
        ee=[e for e in rr if cat=='overall' or e['category']==cat]
        oo=[o for o in row_results if cat=='overall' or o['category']==cat]
        lookup={o['id']:o for o in oo}
        all_pos=17*len(ee);supported=sum(len(e['supported_columns']) for e in ee);core=sum(len(e['core_columns']) for e in ee)
        m={'rows':len(ee),'corresponded':sum(o['correspondence'] for o in oo),'roles_correct':sum(o['role_pass'] for o in oo),'extra_rows_are_not_removed_from_case_gate':True,'modes':{}}
        for mode in ['canonical','normalized','declared_alternatives','declared_alternatives_normalized']:
            total=sum(sum(lookup[e['id']][mode].values()) for e in ee)
            support=sum(sum(lookup[e['id']][mode][c] for c in e['supported_columns']) for e in ee)
            cr=sum(sum(lookup[e['id']][mode][c] for c in e['core_columns']) for e in ee)
            m['modes'][mode]={'all_positions':count(total,all_pos),'supported':count(support,supported),'core':count(cr,core),'whole_rows':count(sum(all(lookup[e['id']][mode].values()) for e in ee),len(ee)),'per_column':{c:count(sum(lookup[e['id']][mode][c] for e in ee if c in e['supported_columns']),sum(c in e['supported_columns'] for e in ee)) for c in COLS}}
        m['raw_literal']=count(sum(sum(o['raw_literal'].values()) for o in oo),6*len(ee))
        m['raw_normalized']=count(sum(sum(o['raw_normalized'].values()) for o in oo),6*len(ee))
        m['nonnull_raw_literal']=count(sum(lookup[e['id']]['raw_literal'][k] for e in ee for k in RAW if e['raw'][k] is not None),sum(e['raw'][k] is not None for e in ee for k in RAW))
        metrics[cat]=m
    modes={mode:all(metrics[cat]['modes'][mode]['core']['percent']>=99 for cat in ['detail','overall']) and not components for mode in ['canonical','normalized','declared_alternatives','declared_alternatives_normalized']}
    provenance=[]
    for e in rr:
        a=paired.get(e['id']);ev=a.get('evidence',{}) if a else {}
        for c in e['supported_columns']:
            field=ev.get(c,{})
            ok=isinstance(field,dict) and (bool(field.get('selection_evidence')) if c=='L' else bool(field.get('location',{}).get('sheet') in {x['sheet'] for x in rr} and field.get('location',{}).get('cells')))
            provenance.append({'id':e['id'],'column':c,'structural_locator_present':ok})
    covered={(n.get('location',{}).get('sheet'),c) for n in carrier.get('nonitems',[]) for c in n.get('location',{}).get('cells',[])}
    ni=[{'sheet':x['sheet'],'cell':x['cell'],'located_in_nonitems':(x['sheet'],x['cell']) in covered} for x in expected.get('nonitem_cell_census',[])]
    return {'schema':'cps.source-comparison043.v1','case_id':expected['case_id'],'metrics':metrics,'row_results':row_results,'correspondence_incidents':incidents,'extra_generated_ids':[x.get('id') for x in extras],'role_defects':role_defects,'component_links':{'matches':sum(x['pass'] for x in link_results),'denominator':0,'records':link_results,'status':'NOT_APPLICABLE_NO_SOURCE_COMPONENTS_NO_PERCENT_CREDIT'},'supported_provenance_locators':{'present':sum(x['structural_locator_present'] for x in provenance),'denominator':len(provenance),'records':provenance,'semantic_correctness':'MANDATORY_MANUAL_REVIEW_PENDING'},'nonitem_cell_locator_coverage':{'covered':sum(x['located_in_nonitems'] for x in ni),'denominator':len(ni),'records':ni,'literal_fidelity':'MANDATORY_MANUAL_REVIEW_PENDING'},'numeric_99_percent_gates':modes,'case_gate':{'source_only_research':True,'complete_row_roles':not incidents and not extras and not role_defects,'all_parent_links':not components and len(link_results)==0,'twelve_semantic_obligations':'MANDATORY_MANUAL_REVIEW_PENDING','zero_critical_errors':'MANDATORY_MANUAL_REVIEW_PENDING','full_semantic_provenance':'MANDATORY_MANUAL_REVIEW_PENDING','source_case_pass':False,'deployment_eligible_pair_credit':0,'reason':'Numeric scores alone cannot satisfy complete semantic/nonitem/provenance/critical-error gates; target eligibility remains unverified.'}}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--expectations',required=True);p.add_argument('--expectations-sha',required=True)
    p.add_argument('--carrier',required=True);p.add_argument('--carrier-sha',required=True)
    p.add_argument('--release',required=True);p.add_argument('--release-sha',required=True)
    p.add_argument('--run',required=True,choices=['A','B']);p.add_argument('--output',required=True)
    a=p.parse_args();assert sha(a.expectations)==a.expectations_sha
    assert sha(a.release)==a.release_sha;release=load(a.release)
    assert release['both_outcomes_frozen'] is True and '1140908' in release['case_ids'] and a.run in release['allowed_runs']
    assert release['reserved_answers_opened'] is False
    # Date parser accepts ISO UTC Z or offset; exact original release bytes remain pinned.
    dt=datetime.datetime.fromisoformat(release['generated_access_released_utc'].replace('Z','+00:00'))
    assert dt.utcoffset()==datetime.timedelta(0)
    frozen=Path(release['generated_output_freeze_path']);assert sha(frozen)==release['generated_output_freeze_sha256']
    pins=load(frozen)['pins'];matches=[x for x in pins if Path(x['path']).resolve()==Path(a.carrier).resolve()]
    assert len(matches)==1 and matches[0]['sha256']==a.carrier_sha and sha(a.carrier)==a.carrier_sha
    expected=load(a.expectations);assert expected['status']=='FROZEN_BEFORE_MODEL_INVOCATION'
    # Carrier bytes are decoded only after release and exact frozen membership checks.
    carrier=load(a.carrier);check_interface(expected,carrier)
    result=evaluate(expected,carrier)
    result['bindings']={'expectations_sha256':a.expectations_sha,'carrier_sha256':a.carrier_sha,'release_sha256':a.release_sha,'run':a.run,'evaluator_sha256':sha(__file__)}
    with Path(a.output).open('x',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'run':a.run,'metrics':result['metrics'],'gates':result['numeric_99_percent_gates']},ensure_ascii=False))
if __name__=='__main__':main()
