"""Read-only characterization of frozen outputs; never a CPS generator or scorer."""
import csv, hashlib, json, re
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=Path('D:/STMS Price Quote')
DATA=ROOT/'exports/CPS_latest_comparison_20261102/selection/COMPARISON_DATA.json'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def pin(p):
    p=Path(p); b=p.read_bytes()
    return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def compact(s): return re.sub(r'\s+','',s or '')
data=read(DATA); records=[]; pins=[pin(DATA)]
assert not data['reserved_answers_opened'] and not data['development_resumed']
for case in data['cases']:
    cp=case['generated_data']; actual=pin(cp['path']); assert actual['sha256']==cp['sha256'];pins.append(actual)
    carrier=read(cp['path']); amap={r['id']:r for r in case['actual_rows']}
    links={p['generated_id']:p for p in case['pairs'] if p.get('generated_id')}
    for kind in ('items','components'):
        for row in carrier.get(kind,[]):
            v=row['values']; raw=row.get('raw',{}); desc=raw.get('description') or ''; remarks=raw.get('remarks') or ''
            c,d=v[2],v[3]; n=compact(c); raw_n=compact(desc)
            position=raw_n.find(n) if n else -1
            pair=links.get(row['id']) if kind=='items' else None
            hist=amap.get(pair.get('actual_id')) if pair else None
            records.append(dict(case_id=case['case_id'],checkpoint=case['checkpoint'],reader=case['reader'],kind=kind,
                item_id=row['id'],raw_description=desc,raw_remarks=remarks,C=c,D=d,I=v[8],J=v[9],unit=v[4],quantity=v[5],
                location=row.get('location'),anchor=row.get('anchor'),
                proof={k:row.get('evidence',{}).get(k) for k in ('C','D','I','J')},
                c_found_in_description_after_whitespace_only=position>=0,
                c_compact_offset=position,prefix_before_c=raw_n[:position] if position>0 else '',
                historical_row=hist['source_row'] if hist else None,
                historical_C=hist['values17'][2] if hist else None,historical_D=hist['values17'][3] if hist else None,
                historical_I=hist['values17'][8] if hist else None,historical_J=hist['values17'][9] if hist else None,
                historical_match_kind=pair.get('status') if pair else None))

groups={}
for r in records: groups.setdefault((r['case_id'],r['kind'],r['item_id']),{})[r['reader']]=r
differences=[]
for key, readers in groups.items():
    assert set(readers)=={'A','B'}
    a,b=readers['A'],readers['B']
    fields=[f for f in ('C','D','I','J','raw_description','raw_remarks') if a[f]!=b[f]]
    if fields: differences.append(dict(case_id=key[0],kind=key[1],item_id=key[2],differing_fields=fields,A={f:a[f] for f in fields},B={f:b[f] for f in fields}))
stats=dict(rows=len(records),unique_source_items=len(groups),main_rows=sum(r['kind']=='items' for r in records),
    component_rows=sum(r['kind']=='components' for r in records),
    C_not_contiguous_after_whitespace_only=sum(not r['c_found_in_description_after_whitespace_only'] for r in records),
    C_follows_prefix=sum(r['c_compact_offset']>0 for r in records),
    historical_linked_output_rows=sum(r['historical_row'] is not None for r in records),
    historical_C_literal_differences=sum(r['historical_row'] is not None and r['historical_C']!=r['C'] for r in records),
    AB_C_different=sum('C' in x['differing_fields'] for x in differences),AB_D_different=sum('D' in x['differing_fields'] for x in differences),
    warning='Mechanical descriptive counts only, not error, translation, semantic correctness or deployment scores.')
for name,obj in [('NAME_INVENTORY.json',records),('AB_NAME_DIFFERENCES.json',differences),('INVENTORY_SUMMARY.json',stats),('INPUT_PINS.json',pins)]:
    (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
keys=['case_id','checkpoint','reader','kind','item_id','raw_description','raw_remarks','C','D','I','J','historical_row','historical_C','historical_D','historical_I','historical_J','c_compact_offset','prefix_before_c']
with (HERE/'NAME_INVENTORY.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(records)
print(json.dumps(stats,ensure_ascii=False,indent=2))
