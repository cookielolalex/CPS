"""Verify exact selected reader packet and mechanical source/cache provenance joins.

Never prints cell values, hints, material expectations or semantic interpretations.
The caller must pin the manifest; the frozen runner binds it to SETUP_FREEZE.
"""
import argparse,hashlib,json,sys
from pathlib import Path
from strict_input import strict_load,read_bounded,source_shape,address,bounds
from source_verify import verify_source,need

def check_pin(pin,limit):
    need(type(pin) is dict and set(pin)=={'path','bytes','sha256'},'PACKET_PIN_SHAPE')
    p=Path(pin['path']);need(p.is_absolute() and str(p.resolve(strict=True)).casefold()==str(p).casefold(),'PACKET_PATH_REDIRECTION')
    raw=read_bounded(p,limit)
    need(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'PACKET_PIN_MISMATCH')
    return raw

def verify_packet(manifest):
    source=manifest['source'];source_shape(source)
    need(source['kind']=='cached_xls','LEGACY_READER_REQUIRED')
    source_pin=manifest['original_source_pin']
    need(source_pin['path']==source['path'] and source_pin['sha256']==source['sha256'],'ORIGINAL_SOURCE_PIN_JOIN')
    raw=check_pin(manifest['literal_reader_data'],20*1024*1024)
    pins=[manifest['literal_reader_data']]+manifest['images']
    need(len(manifest['images'])==len(source['views']) and manifest['allowed_generation_inputs']==[p['path'] for p in pins],'EXACT_READER_ALLOWLIST_JOIN')
    need(len(set(p['path'].casefold() for p in pins))==len(pins),'DUPLICATE_READER_INPUT')
    for pin in manifest['images']:
        img=check_pin(pin,20*1024*1024);need(img.startswith(b'\x89PNG\r\n\x1a\n'),'PNG_SIGNATURE_REQUIRED')
    d=strict_load(raw,20*1024*1024)
    need(d['schema']=='cps.cached-legacy-xls-reader-data043.v1','LEGACY_READER_SCHEMA')
    need(d['case_id']==manifest['case_id'] and d['family_id']==manifest['family_id'],'READER_CASE_JOIN')
    rs=d['source'];need(all(rs[k]==source[k] for k in ('kind','path','sha256')),'READER_SOURCE_JOIN')
    need([{k:v[k] for k in ('id','sheet','range')} for v in rs['views']]==source['views'],'READER_VIEWS_JOIN')
    report,book,formula=verify_source(source,return_book=True)
    need(report['bytes']==source_pin['bytes'],'ORIGINAL_SOURCE_SIZE_JOIN')
    need(d['sheet_names']==book.sheet_names(),'READER_SHEETS_JOIN')
    sheets={s.name:s for s in book.sheets()};formula_coords={s.name:{(r,c) for r,c,_ in formula[i]} for i,s in enumerate(book.sheets())}
    seen=set();positions=0;types={};formulas=0
    for row in d['rows']:
        need(type(row) is dict and set(row)=={'sheet','row','cells','views'},'READER_ROW_SHAPE')
        name=row['sheet'];need(name in sheets and type(row['row']) is int,'READER_ROW_JOIN');s=sheets[name]
        need(1<=row['row']<=s.nrows and len(row['cells'])==s.ncols,'READER_PHYSICAL_ROW_JOIN')
        expected_views=[v['id'] for v in source['views'] if v['sheet']==name and bounds(v['range'])[0][1]<=row['row']<=bounds(v['range'])[1][1]]
        need(row['views']==expected_views,'READER_ROW_VIEW_JOIN')
        for index,c in enumerate(row['cells']):
            need(type(c) is dict and set(c)=={'cell','value','saved_cell_type','formula_record_present'},'READER_CELL_SHAPE')
            col,r=address(c['cell']);need(r==row['row'] and col==index+1,'READER_CELL_POSITION_JOIN')
            key=(name,r,col);need(key not in seen,'READER_DUPLICATE_POSITION');seen.add(key)
            typ=s.cell_type(r-1,col-1);value=s.cell_value(r-1,col-1)
            expected_value=None if typ in (0,6) else value
            need(type(c['saved_cell_type']) is int and c['saved_cell_type']==typ,'READER_CELL_TYPE_JOIN')
            if typ in (2,3):need(type(c['value']) in (int,float) and c['value']==value,'READER_NUMERIC_CACHE_JOIN')
            else:need(type(c['value']) is type(expected_value) and c['value']==expected_value,'READER_LITERAL_CACHE_JOIN')
            present=(r-1,col-1) in formula_coords[name]
            need(type(c['formula_record_present']) is bool and c['formula_record_present']==present,'READER_FORMULA_FLAG_JOIN')
            formulas+=int(present);positions+=1;types[str(typ)]=types.get(str(typ),0)+1
    need(positions==sum(s.nrows*s.ncols for s in sheets.values()),'READER_COMPLETE_PHYSICAL_CENSUS')
    return {'status':'EXACT_READER_AND_ORIGINAL_PROVENANCE_JOINED','source':report,'reader_inputs':pins,'positions_verified':positions,'saved_types':types,'formula_record_flags_verified':formulas,'material_values_printed':False,'formula_recalculated':False,'semantic_accuracy':None,'source_adoption_verified':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    raw=read_bounded(a.manifest,256*1024);result=verify_packet(strict_load(raw,256*1024));result['manifest_sha256']=hashlib.sha256(raw).hexdigest()
    with Path(a.report).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source','reader_inputs')},ensure_ascii=False))
if __name__=='__main__':main()
