"""Verify mechanical source citation and repeatability from runtime outputs only.

Never opens source workbooks or historical targets. Not a semantic audit.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import cps

def verify(directory,repeat=None):
    directory=Path(directory);receipt=json.loads((directory/'BATCH_RECEIPT.json').read_text(encoding='utf-8'))
    cases=[];errors=[]
    for entry in receipt['outputs']:
        path=directory/(entry['case_id']+'.json')
        if cps.sha(path)!=entry['sha256']: errors.append(entry['case_id']+': output hash mismatch')
        b=json.loads(path.read_text(encoding='utf-8'));lookup={};states=Counter();kinds=Counter()
        for s in b['sheets']:
            for d in s['row_dispositions']:
                kinds[d['kind']]+=1
                for c in d['raw_cells']:
                    lookup[(s['source_path'],s['name'],c['cell'])]=c
                    states[c['state']]+=1
        populated=0;citations=0;missing=[];ids=[]
        for r in b['rows']:
            ids.append(r['id'])
            if len(r['values'])!=17: errors.append(r['id']+': incorrect column count')
            for letter,value in zip(cps.LETTERS,r['values']):
                if value is None or value=='': continue
                populated+=1;p=r['field_provenance'].get(letter,{})
                if letter=='L' and p.get('basis') and p.get('namespace')=='internal project identifier':
                    citations+=1
                    if value!=p.get('value'): errors.append(r['id']+': L declared identifier mismatch')
                    continue
                if not p.get('sources'): missing.append(r['id']+':'+letter);continue
                citations+=1
                for c in p['sources']:
                    actual=lookup.get((c['source_path'],c['sheet'],c['cell']))
                    if actual is None or actual.get('raw')!=c.get('raw') or actual.get('cached')!=c.get('cached') or actual['state']!=c['state']:
                        errors.append(r['id']+':'+letter+': citation does not match output source snapshot')
                if letter in ['E','F','I','J','K'] and value!=cps.cellvalue(p['sources'][0]): errors.append(r['id']+':'+letter+': copy differs')
                if letter=='Q' and value!=cps.numeric(cps.cellvalue(p['sources'][0])): errors.append(r['id']+': Q exact numeric source value differs')
                if letter in ['A','B'] and value!='\n'.join(str(cps.cellvalue(c)) for c in p['sources']): errors.append(r['id']+': '+letter+' ordered title/specification fragments differ')
                if letter=='C' and value!='\n'.join(str(cps.cellvalue(c)) for c in p['sources']): errors.append(r['id']+': C ordered-fragment mismatch')
                if letter=='D':
                    parts=[c for key in ['spec','remark'] for c in p['sources'] if c.get('stream')==key]
                    if value!='\n'.join(str(cps.cellvalue(c)) for c in parts): errors.append(r['id']+': D independent-stream mismatch')
        if len(ids)!=len(set(ids)): errors.append(entry['case_id']+': duplicate IDs')
        if missing: errors.extend(missing)
        repeat_match=None
        if repeat:
            candidate=Path(repeat)/path.name
            repeat_match=candidate.exists() and cps.sha(candidate)==cps.sha(path)
            if not repeat_match: errors.append(entry['case_id']+': repeat hash mismatch')
        cases.append({'case_id':entry['case_id'],'status':b['status'],'counts':b['counts'],'coverage_complete':b['coverage_complete'],'populated_fields':populated,'fields_with_structural_citation':citations,'source_cell_states':dict(states),'row_disposition_counts':dict(kinds),'panel_groups':sum(len(s['groups']) for s in b['sheets']),'analysis_blocks':len(b['analysis_blocks']),'exact_repeat_hash_match':repeat_match,'sha256':cps.sha(path)})
    return {'schema_version':1,'verification':'PASS' if not errors else 'FAIL','meaning':'Mechanical citation correspondence, column/ID structure, physical-row accounting and optional exact repeat only; no semantic acceptance.','errors':errors,'case_count':len(cases),'generated_rows':sum(x['counts']['generated_rows'] for x in cases),'source_rows':sum(x['counts']['source_rows'] for x in cases),'statuses':dict(Counter(x['status'] for x in cases)),'cases':cases,'historical_targets_read':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--repeat');p.add_argument('--output',required=True);a=p.parse_args()
    result=verify(a.run,a.repeat);cps.write_json(a.output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False,indent=2))
