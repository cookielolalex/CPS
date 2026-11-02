"""Mechanical expansion of explicitly model-authored facts. No source or answer access."""
import copy
import re
import json
from strict_input import strict_load,source_shape,location

LIMIT = 20 * 1024 * 1024
COLS = 'ABCDEFGHIJKLMNOPQ'
HEADERS = ['盤體名稱','盤體規格','材料名稱','規格','單位','數量','單價','複價','型號','廠牌','訂購廠商','工程編號','訂購客戶','使用客戶','需要日期','需要數量','合約價']
RAW = ['description','unit','quantity','unit_price','amount','remarks']
TOP = {'schema','case_id','family_id','source','metadata','groups','items','components','nonitems','limitations','evidence','reasons','fieldsets'}

def need(ok, code):
    if not ok: raise ValueError(code)

def text(v):
    need(type(v) is str and bool(v.strip()), 'NONEMPTY_STRING_REQUIRED')
    return v

def ident(v):
    text(v);need(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',v)), 'ID_REQUIRED')
    return v

def dictionary(v, maximum):
    need(type(v) is dict and len(v)<=maximum,'DICTIONARY_LIMIT_OR_TYPE')
    for key in v: ident(key)

def array(v,n=None,maximum=None):
    need(type(v) is list,'ARRAY_REQUIRED')
    if n is not None: need(len(v)==n,'EXACT_ARRAY_LENGTH_REQUIRED')
    if maximum is not None: need(len(v)<=maximum,'ARRAY_LIMIT')

def fieldmap(v):
    need(type(v) is dict and len(v)<=17 and all(k in COLS and len(k)==1 for k in v),'FIELD_MAP_REQUIRED')
    for pair in v.values(): array(pair,2)

def decode(envelope):
    outer=strict_load(envelope,LIMIT)
    need(type(outer) is dict and set(outer)=={'compact_json'} and type(outer['compact_json']) is str,'EXACT_COMPACT_ENVELOPE_REQUIRED')
    raw=outer['compact_json'].encode('utf-8')
    need(len(raw)<=LIMIT,'COMPACT_SIZE_LIMIT')
    return raw,strict_load(raw,LIMIT)

def encode_bounded(value,limit=LIMIT):
    """Cap bytes while serializing; never build an unbounded expanded JSON string."""
    encoded=bytearray()
    encoder=json.JSONEncoder(ensure_ascii=False,separators=(',',':'),allow_nan=False)
    for chunk in encoder.iterencode(value):
        data=chunk.encode('utf-8')
        need(len(encoded)+len(data)<=limit,'EXPANDED_CARRIER_SIZE_LIMIT')
        encoded.extend(data)
    return bytes(encoded)

def expand(c):
    need(type(c) is dict and set(c)==TOP,'EXACT_COMPACT_KEYS_REQUIRED')
    source_shape(c['source'])
    legacy=c['source']['kind']=='cached_xls'
    need(c['schema']==('cps.compact-cached-xls.v1' if legacy else 'cps.compact-cached-xlsx.v1'),'COMPACT_SOURCE_SCHEMA_MISMATCH')
    for kind,maximum in [('evidence',20000),('reasons',2000),('fieldsets',2000)]:dictionary(c[kind],maximum)
    for proof in c['evidence'].values():
        array(proof);need(len(proof) in (2,4),'EVIDENCE_DICTIONARY_TUPLE_REQUIRED')
    for value in c['reasons'].values():text(value)
    for value in c['fieldsets'].values():fieldmap(value)
    array(c['items'],maximum=2000);need(bool(c['items']),'ITEMS_REQUIRED')
    array(c['components'],maximum=2000)
    array(c['nonitems'],maximum=5000)
    source_shape(c['source'])
    used={kind:set() for kind in ['evidence','reasons','fieldsets']}
    mapping=[]
    def page(p):location(p,c['source'])
    def evidence(proof,col,row,trace):
        if type(proof) is dict and set(proof)=={'ref'}:
            ref=ident(proof['ref']);need(ref in c['evidence'],'UNKNOWN_EVIDENCE_REF')
            used['evidence'].add(ref);trace['evidence_ref']=ref;proof=c['evidence'][ref]
        if type(proof) is dict:
            need(set(proof)=={'raw','transformation'},'EXACT_RAW_REFERENCE_REQUIRED')
            idx=proof['raw'];need(type(idx) is int and 0<=idx<6,'RAW_INDEX_OUT_OF_RANGE')
            literal=text(row[4][idx]);trace['raw_index']=idx
            return {'location':row[2],'anchor':row[3],'raw_text':literal,'transformation':text(proof['transformation'])}
        array(proof)
        if len(proof)==2:
            need(col=='L','SELECTION_EVIDENCE_ONLY_L')
            return {'selection_evidence':text(proof[0]),'transformation':text(proof[1])}
        array(proof,4);page(proof[0])
        return dict(zip(['location','anchor','raw_text','transformation'],[proof[0],text(proof[1]),text(proof[2]),text(proof[3])]))
    items=[];seen=set()
    for ri,fullrow in enumerate(c['items']+c['components']):
        is_component=ri>=len(c['items'])
        array(fullrow,10 if is_component else 9)
        row=fullrow[:9]
        rid=ident(row[0]);need(rid not in seen,'DUPLICATE_ITEM_ID');seen.add(rid)
        page(row[2]);text(row[3]);array(row[4],6)
        need(all(v is None or type(v) is str for v in row[4]),'RAW_STRING_OR_NULL_REQUIRED')
        array(row[5],maximum=17);fieldmap(row[6])
        need(all(type(x) is str for x in row[5]) and len(set(row[5]))==len(row[5]),'UNIQUE_FIELDSET_IDS_REQUIRED')
        fields={};origins={}
        for ref in row[5]:
            ident(ref);need(ref in c['fieldsets'],'UNKNOWN_FIELDSET_REF');used['fieldsets'].add(ref)
            for col,pair in c['fieldsets'][ref].items():
                need(col not in fields,'OVERLAPPING_FIELD_DECLARATION');fields[col]=pair;origins[col]='fieldset:'+ref
        for col,pair in row[6].items():
            need(col not in fields,'OVERLAPPING_FIELD_DECLARATION');fields[col]=pair;origins[col]='row'
        need(set(fields)==set(COLS),'ALL_SEVENTEEN_COLUMNS_REQUIRED')
        values=[];ev={};nulls={}
        for col in COLS:
            val,proof=fields[col];trace={'item':rid,'column':col,'origin':origins[col]}
            need(val is None or type(val) in (str,int,float),'CELL_VALUE_TYPE')
            if val is None:
                if type(proof) is dict:
                    need(set(proof)=={'ref'},'EXACT_REASON_REFERENCE_REQUIRED')
                    ref=ident(proof['ref']);need(ref in c['reasons'],'UNKNOWN_REASON_REF')
                    used['reasons'].add(ref);trace['reason_ref']=ref;proof=c['reasons'][ref]
                nulls[col]=text(proof)
            else:ev[col]=evidence(proof,col,row,trace)
            values.append(copy.deepcopy(val));mapping.append(trace)
        items.append(dict(zip(['id','group_id','location','anchor','raw','values','evidence','null_reasons','status','review_reasons'],[row[0],row[1],row[2],row[3],dict(zip(RAW,copy.deepcopy(row[4]))),values,ev,nulls,row[7],copy.deepcopy(row[8])])))
        if is_component:items[-1]['composition']=copy.deepcopy(fullrow[9])
    nonitems=[]
    for row in c['nonitems']:
        array(row,5);page(row[0]);nonitems.append(dict(zip(['location','kind','anchor','text','reason'],copy.deepcopy(row))))
    for kind in used:need(used[kind]==set(c[kind]),'UNUSED_'+kind.upper()+'_DECLARATION')
    result={k:copy.deepcopy(c[k]) for k in ['case_id','family_id','source','metadata','groups','limitations']}
    result.update(schema=('cps.cached-xls-research-carrier.v1' if legacy else 'cps.cached-xlsx-research-carrier.v1'),headers=HEADERS.copy(),items=items[:len(c['items'])],components=items[len(c['items']):],nonitems=nonitems)
    return result,mapping
