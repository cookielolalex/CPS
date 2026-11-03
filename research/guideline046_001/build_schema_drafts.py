"""Author generic JSON data contracts only; not a parser, resolver or evaluator."""
import json
from pathlib import Path
P=Path(__file__).resolve().parent/'package/resources'
def obj(props,required=None):
    return dict(type='object',properties=props,required=list(props) if required is None else required,additionalProperties=False)
def arr(item,**kw): return dict(type='array',items=item,**kw)
def enum(*values): return dict(enum=list(values))
def ref(name): return {'$ref':f'#/$defs/{name}'}
text={'type':'string'}
nonempty={'type':'string','minLength':1}
digest={'type':'string','pattern':'^[0-9a-f]{64}$'}
nullable_text={'type':['string','null']}
scalar={'type':['string','number','null']}
saved_scalar={'type':['string','number','boolean','null']}
reference={'type':'string','pattern':'^(cell|context):[^\\s]+$'}
cell_reference={'type':'string','pattern':'^cell:[^\\s]+$'}
column={'type':'string','enum':list('ABCDEFGHIJKLMNOPQ')}
role=enum('demand_content','analysis_content','item_identifier','header','section','financial_summary','commercial_note','document_reference','footer','unresolved')

source=obj(dict(source_id=nonempty,path=nonempty,sha256=digest,format=enum('xlsx','cached_xls','ods'),
    adoption_status=enum('verified','partial','unverified'),adoption_basis=nonempty,scope=arr(nonempty,minItems=1)))
cell=obj(dict(ref=cell_reference,source_id=nonempty,sheet=nonempty,address={'type':'string','pattern':'^[A-Z]+[1-9][0-9]*$'},
    state=enum('literal','cached_formula','true_blank','explicit_empty','covered','error','missing_cache','unresolved'),
    saved_value=saved_scalar,saved_type=nonempty,formula=nullable_text,cache=saved_scalar,
    merge_anchor_ref={'type':['string','null']},conflicts=arr(nonempty),canonical_raw=nullable_text,
    usable_for_raw={'type':'boolean'},raw_limit_reason=nullable_text))
context=obj(dict(ref={'type':'string','pattern':'^context:[^\\s]+$'},namespace=nonempty,value=scalar,
    basis=nonempty,authority_pins=arr(obj(dict(path=nonempty,sha256=digest)),minItems=1)))
inventory=obj(dict(schema=enum('cps.source-inventory.cells.draft.v1'),case_id=nonempty,
    representation_profile=enum('cached-cell-raw-scalar-text.draft.v1'),sources=arr(ref('source'),minItems=1),
    cells=arr(ref('cell'),minItems=1),context_facts=arr(ref('context')),limitations=arr(nonempty)))
inventory.update({'$schema':'https://json-schema.org/draft/2020-12/schema',
    '$id':'urn:cps:source-inventory:cells:draft:v1',
    '$defs':dict(source=source,cell=cell,context=context),
    'description':'DRAFT structural contract only. Unique and cross-reference identity, source bytes, semantic roles, representation and adapter correctness require separate reviewed guards.'})

nonnull_proof=obj(dict(refs=arr(reference,minItems=1,uniqueItems=True),transformation=nonempty,role_basis=nonempty))
null_proof=obj(dict(reason=nonempty))
proof={'oneOf':[ref('nonnull_proof'),ref('null_proof')]}
raw_selection=obj(dict(refs=arr(cell_reference,uniqueItems=True),reason_if_empty=nullable_text))
item=obj(dict(id=nonempty,role=enum('demand','analysis_component'),status=enum('research_draft','partial','held'),
    values=arr(scalar,minItems=17,maxItems=17),proofs=obj({k:proof for k in 'ABCDEFGHIJKLMNOPQ'}),
    raw_refs=obj({k:ref('raw_selection') for k in ['description','unit','quantity','unit_price','amount','remarks']}),
    anchor_refs=arr(cell_reference,minItems=1,uniqueItems=True),review_reasons=arr(nonempty)))
link=obj(dict(component_id=nonempty,parent_id=nullable_text,status=enum('supported','held'),
    basis={'type':['number','null'],'exclusiveMinimum':0},refs=arr(cell_reference,uniqueItems=True),reason=nonempty))
roles=obj(dict(role=role,refs=arr(cell_reference,minItems=1,uniqueItems=True),reason=nonempty))
response=obj(dict(schema=enum('cps.semantic-source-refs.draft.v1'),case_id=nonempty,inventory_sha256=digest,
    status=enum('research_draft','partial','held'),items=arr(ref('item')),component_links=arr(ref('component_link')),
    source_roles=arr(ref('source_role')),limitations=arr(nonempty)))
response.update({'$schema':'https://json-schema.org/draft/2020-12/schema',
    '$id':'urn:cps:semantic-source-refs:draft:v1',
    '$defs':dict(nonnull_proof=nonnull_proof,null_proof=null_proof,raw_selection=raw_selection,item=item,component_link=link,source_role=roles),
    'description':'DRAFT structural contract. Array positions map A-Q. Null/value-proof consistency, unique/cross-role references, type/precision, stage blanks, coverage and semantic support require reviewed guards; schema conformance alone is not acceptance.'})
for name,data in [('SOURCE_INVENTORY.schema.json',inventory),('SEMANTIC_RESPONSE.schema.json',response)]:
    (P/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
columns=['盤體名稱','盤體規格','材料名稱','規格','單位','數量','單價','複價','型號','廠牌','訂購廠商','工程編號','訂購客戶','使用客戶','需要日期','需要數量','合約價']
(P/'COLUMNS.json').write_text(json.dumps(dict(schema='cps.columns.v1',columns=[dict(index=i+1,letter=chr(65+i),label=x) for i,x in enumerate(columns)]),ensure_ascii=False,indent=2),encoding='utf-8')
print('Authored two draft schemas and17-column mapping; no resolver/model execution.')
