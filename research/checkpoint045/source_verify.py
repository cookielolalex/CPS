"""Read-only original workbook identity/type verification; no material output."""
import argparse, contextlib, hashlib, io, json, math, ntpath, re, struct, sys, unicodedata
from pathlib import Path

LIMIT = 100 * 1024 * 1024
DEPENDENCY_ROOT = Path(r'D:\CPS_LOCAL_WORKSPACE\runs\CONTRACT-WEITIAN-20261030-001\deps')
DEPENDENCY_PIN_SHA = 'fd8592863c37f033a87300c49e744137139c285f6b073a710c6d6b04147a1499'
KINDS = {'cached_xls': '.xls', 'cached_xlsx': '.xlsx'}
FORBIDDEN = re.compile(r'未填|已填|電機圖|板金|鈑金|歷史|(?:^|[\\/_. -])(?:ok|targets?|reserved|drawings?|histor(?:y|ical|ies))(?=[\\/_. -]|$)', re.I)
DEVICE = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',re.I)

def need(ok, code):
    if not ok: raise ValueError(code)

def canonical_path(value,kind):
    need(kind in KINDS,'SOURCE_KIND')
    need(type(value) is str and len(value)<=2048,'PATH_REQUIRED')
    need(unicodedata.normalize('NFC',value)==value,'NONCANONICAL_UNICODE_PATH')
    need(bool(re.match(r'^[A-Z]:\\',value)) and '/' not in value,'CANONICAL_LOCAL_ABSOLUTE_PATH_REQUIRED')
    parts=value[3:].split('\\')
    need(bool(parts) and all(p and p not in ('.','..') and p[-1] not in ' .' and not re.search(r'[<>:"|?*\x00-\x1f]',p) and not DEVICE.match(p) for p in parts),'NONCANONICAL_PATH_COMPONENT')
    need(ntpath.normpath(value)==value and ntpath.splitext(value)[1].lower()==KINDS[kind],'SOURCE_KIND_EXTENSION_MISMATCH')
    need(not FORBIDDEN.search(value),'FORBIDDEN_SOURCE_PATH')
    return value

def bounded(path,limit=LIMIT):
    with Path(path).open('rb') as f: data=f.read(limit+1)
    need(len(data)<=limit,'SOURCE_FILE_LIMIT')
    return data

def load_xlrd():
    binding=Path(__file__).with_name('DEPENDENCY_PINS.json')
    raw=bounded(binding,256*1024)
    need(hashlib.sha256(raw).hexdigest()==DEPENDENCY_PIN_SHA,'DEPENDENCY_BINDING_CHANGED')
    pins=json.loads(raw)['xlrd_python_sources']
    actual=sorted(str(p) for p in (DEPENDENCY_ROOT/'xlrd').glob('*.py'))
    need(actual==sorted(p['path'] for p in pins),'DEPENDENCY_MEMBERS_CHANGED')
    for pin in pins:
        p=Path(pin['path']);need(str(p.resolve(strict=True)).casefold()==str(p).casefold(),'DEPENDENCY_REDIRECTION')
        b=bounded(p,2*1024*1024);need(len(b)==pin['bytes'] and hashlib.sha256(b).hexdigest()==pin['sha256'],'DEPENDENCY_CHANGED')
    sys.path.insert(0,str(DEPENDENCY_ROOT))
    import xlrd
    need(Path(xlrd.__file__).resolve()==(DEPENDENCY_ROOT/'xlrd/__init__.py').resolve(),'DEPENDENCY_IMPORT_REDIRECTION')
    need(xlrd.__version__=='2.0.2','DEPENDENCY_VERSION')
    return xlrd

def substream(stream,start,expected_type):
    need(0<=start and start+8<=len(stream),'BIFF_SUBSTREAM_BOUNDS')
    op,n=struct.unpack_from('<HH',stream,start)
    need(op==0x0809 and n>=8 and start+4+n<=len(stream),'BIFF8_BOF_REQUIRED')
    version,kind=struct.unpack_from('<HH',stream,start+4)
    need(version==0x0600 and kind==expected_type,'BIFF8_SUBSTREAM_TYPE_REQUIRED')
    pos=start;records=[]
    while pos+4<=len(stream):
        op,n=struct.unpack_from('<HH',stream,pos)
        need(n<=8224 and pos+4+n<=len(stream),'BIFF_RECORD_TRUNCATED_OR_OVERSIZED')
        body=stream[pos+4:pos+4+n];records.append((op,pos,body));pos+=4+n
        need(len(records)<=1000000,'BIFF_RECORD_LIMIT')
        if op==0x000a:
            need(n==0,'BIFF_EOF_LENGTH');return records,pos
    raise ValueError('BIFF_EOF_REQUIRED')

def parse_legacy(raw):
    need(raw.startswith(bytes.fromhex('d0cf11e0a1b11ae1')),'XLS_OLE_SIGNATURE_REQUIRED')
    xlrd=load_xlrd()
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        try:
            compound=xlrd.compdoc.CompDoc(raw,logfile=io.StringIO())
            stream=compound.get_named_stream('Workbook')
            need(stream is not None,'OLE_WORKBOOK_STREAM_REQUIRED')
            globals_,end=substream(stream,0,0x0005)
            need(not any(op==0x002f for op,_,_ in globals_),'ENCRYPTED_WORKBOOK_UNSUPPORTED')
            starts=[]
            for op,_,body in globals_:
                if op==0x0085:
                    need(len(body)>=8,'BOUNDSHEET_TRUNCATED')
                    need(body[5]==0,'NON_WORKSHEET_SUBSTREAM_UNSUPPORTED')
                    starts.append(struct.unpack_from('<I',body)[0])
            need(1<=len(starts)<=1000 and len(set(starts))==len(starts),'WORKSHEET_STREAMS_REQUIRED')
            formula=[];ranges=[]
            for start in starts:
                need(start>=end,'BIFF_OVERLAPPING_SUBSTREAM')
                records,stop=substream(stream,start,0x0010);ranges.append((start,stop))
                ff=[]
                for op,offset,body in records:
                    if op==6:
                        need(len(body)>=22,'FORMULA_RECORD_TRUNCATED')
                        r,c=struct.unpack_from('<HH',body);tokens=struct.unpack_from('<H',body,20)[0]
                        need(tokens<=len(body)-22,'FORMULA_TOKENS_TRUNCATED')
                        ff.append((r,c,body[6:14]))
                formula.append(ff)
            ordered=sorted(ranges)
            need(all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:])),'BIFF_OVERLAPPING_SUBSTREAM')
            book=xlrd.open_workbook(file_contents=raw,formatting_info=True,on_demand=True,logfile=io.StringIO(),ignore_workbook_corruption=False)
            need(book.biff_version==80 and book.nsheets==len(starts),'BIFF8_XLRD_AGREEMENT_REQUIRED')
            census=[]
            for i,sheet in enumerate(book.sheets()):
                ff=formula[i];seen=set();counts={}
                for row,col,cached in ff:
                    need((row,col) not in seen and row<sheet.nrows and col<sheet.ncols,'FORMULA_COORDINATE_INVALID');seen.add((row,col))
                    typ=sheet.cell_type(row,col);counts[str(typ)]=counts.get(str(typ),0)+1
                    if cached[-2:]!=b'\xff\xff':
                        number=struct.unpack('<d',cached)[0]
                        need(math.isfinite(number) and typ in (2,3) and sheet.cell_value(row,col)==number,'NUMERIC_FORMULA_CACHE_MISMATCH')
                census.append({'sheet':sheet.name,'rows':sheet.nrows,'columns':sheet.ncols,'formula_records':len(ff),'formula_cached_types':counts})
            return book,formula,{'format':'BIFF8_OLE_WORKBOOK','biff_version':80,'worksheets':census,'formula_expression_evaluated':False,'macro_execution':False,'external_link_updates':False,'recalculations':0}
        except ValueError: raise
        except Exception as e: raise ValueError('INVALID_BIFF8_WORKBOOK:'+type(e).__name__) from None

def verify_source(source,return_book=False):
    need(type(source) is dict and set(source)=={'kind','path','sha256','views'},'SOURCE_SHAPE')
    canonical_path(source['path'],source['kind'])
    need(type(source['sha256']) is str and bool(re.fullmatch('[0-9a-f]{64}',source['sha256'])),'SOURCE_HASH_SHAPE')
    p=Path(source['path']);real=str(p.resolve(strict=True));canonical_path(real,source['kind'])
    need(real.casefold()==source['path'].casefold(),'SOURCE_REDIRECTION')
    need(p.is_file(),'SOURCE_FILE_REQUIRED');raw=bounded(p)
    need(hashlib.sha256(raw).hexdigest()==source['sha256'],'SOURCE_HASH_MISMATCH')
    book=formula=None
    if source['kind']=='cached_xls': book,formula,format_info=parse_legacy(raw)
    else:
        need(raw.startswith(b'PK\x03\x04'),'XLSX_SIGNATURE_REQUIRED')
        format_info={'format':'XLSX_ZIP_SIGNATURE','content_validation':'UNCHANGED_XLSX_SIGNATURE_ONLY'}
    result={'path':source['path'],'kind':source['kind'],'sha256':source['sha256'],'bytes':len(raw),'format_validation':format_info,'cached_cells_semantically_verified':False,'semantic_source_approval':False,'native_display_verified':False}
    return (result,book,formula) if return_book else result

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-stdin',action='store_true',required=True);a=p.parse_args()
    raw=sys.stdin.buffer.read(256*1024+1);need(len(raw)<=256*1024,'SOURCE_JSON_LIMIT')
    print(json.dumps(verify_source(json.loads(raw)),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'status':'REJECTED','reason':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
