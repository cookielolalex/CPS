"""Bounded, read-only spreadsheet container/ODS readers; no recalculation.

The first ODS pass discards cell text and every cell value/formula attribute
as raw bytes, before XML decoding. Only namespace and table-name metadata
survives that pass. All table names must pass the caller's guard before the
original XML is parsed. OLE similarly exposes only BIFF8 BOUNDSHEET names
before xlrd may decode its SST or any worksheet.
"""
from __future__ import annotations
import io
import hashlib
import math
import posixpath
import re
import struct
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_ZIP_MEMBERS = 2048
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_XML_NODES = 300000
MAX_XML_DEPTH = 128
MAX_SHEETS = 128
MAX_ROWS = 20000
MAX_COLUMNS = 1024
MAX_CELLS = 1000000
MAX_LOGICAL_ROWS = 1048576
MAX_LOGICAL_COLUMNS = 16384
MAX_TEXT = 131072
MAX_INERT_BIFF_RECORDS = 4096
MAX_INERT_BIFF_BYTES = 1024 * 1024
MAX_BIFF_RECORD_BYTES = 8224
BIFF_NONMATERIALIZING = {
    0x089C: ('HeaderFooter', 'MS-XLS 2.4.137'),
    0x088B: ('PLV', 'MS-XLS 2.4.200'),
    0x01C2: ('EntExU2', 'MS-XLS 2.4.102'),
    0x0874: ('DropDownObjIds', 'MS-XLS 2.4.93'),
}
ODS_MIME = b'application/vnd.oasis.opendocument.spreadsheet'
OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
NS = {'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
      'table':'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
      'text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
      'style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
      'xlink':'http://www.w3.org/1999/xlink',
      'calcext':'urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0'}
def q(prefix, local): return '{'+NS[prefix]+'}'+local
def colname(i):
    out=''
    while i: i,k=divmod(i-1,26);out=chr(65+k)+out
    return out

def source_bytes(path):
    with Path(path).open('rb') as f: data=f.read(MAX_SOURCE_BYTES+1)
    if len(data)>MAX_SOURCE_BYTES: raise ValueError('Source byte limit exceeded')
    return data

def checked_zip(data):
    z=zipfile.ZipFile(io.BytesIO(data))
    try:
        members=z.infolist(); names=[i.filename for i in members]
        if len(members)>MAX_ZIP_MEMBERS or len(names)!=len(set(names)):
            raise ValueError('ZIP member count/duplicate limit')
        if sum(i.file_size for i in members)>MAX_ZIP_BYTES: raise ValueError('ZIP decompressed byte limit')
        for i in members:
            if i.file_size>MAX_XML_BYTES: raise ValueError('ZIP member byte limit')
            if i.flag_bits & 1: raise ValueError('Encrypted ZIP unsupported')
            if i.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED): raise ValueError('Unsupported ZIP compression')
            if i.filename.startswith(('/', '\\')) or '\\' in i.filename or '..' in i.filename.split('/'):
                raise ValueError('Unsafe ZIP member path')
        return z
    except Exception:
        z.close();raise

def zip_member(z, name, limit=MAX_XML_BYTES):
    info=z.getinfo(name)
    if info.file_size>limit: raise ValueError('ZIP member byte limit: '+name)
    with z.open(info) as f: data=f.read(limit+1)
    if len(data)>limit or len(data)!=info.file_size: raise ValueError('ZIP member size mismatch/limit')
    return data

def detect_container(data):
    if data.startswith(OLE_MAGIC): return 'BIFF8_OLE'
    if not data.startswith(b'PK\x03\x04'): raise ValueError('Unknown spreadsheet container; source blocked')
    with checked_zip(data) as z:
        names=set(z.namelist())
        mime=zip_member(z,'mimetype',256) if 'mimetype' in names else None
        ods=mime==ODS_MIME and {'content.xml','META-INF/manifest.xml'}<=names
        xlsx={'[Content_Types].xml','xl/workbook.xml','xl/_rels/workbook.xml.rels'}<=names
        if ods and xlsx: raise ValueError('Ambiguous mixed spreadsheet containers')
        if ods: return 'ODS_ZIP'
        if xlsx and mime is None: return 'OOXML_ZIP'
    raise ValueError('Unknown ZIP spreadsheet container; source blocked')

_NAME=rb'[A-Za-z_][A-Za-z0-9_.:-]*'
_ATTR=re.compile(rb'\s+('+_NAME+rb')\s*=\s*("[^"]*"|\x27[^\x27]*\x27)')
def metadata_skeleton(data, keep_grid=False):
    """Return XML structural/name metadata without decoding any cell strings.

    Tokenization is byte-only, quote-aware and bounded. DTDs/entities are
    forbidden. Namespaces are retained even on nested elements, preventing
    prefix-rebinding from disguising a forbidden table. Text and nonmetadata
    attributes never enter an XML parser during this phase.
    """
    if len(data)>MAX_XML_BYTES: raise ValueError('XML byte limit')
    if data.startswith((b'\xff\xfe',b'\xfe\xff')) or b'\x00' in data:
        raise ValueError('Only UTF-8 ODS XML is supported')
    declaration=re.match(rb'\xef\xbb\xbf\s*<\?xml\b.*?\?>|\s*<\?xml\b.*?\?>',data,re.S)
    if declaration:
        encoding=re.search(rb'encoding\s*=\s*[\x22\x27]([^\x22\x27]+)',declaration[0],re.I)
        if encoding and encoding[1].lower() not in (b'utf-8',b'utf8'): raise ValueError('Only UTF-8 ODS XML is supported')
    out=[];at=0;nodes=0;depth=0
    while True:
        begin=data.find(b'<',at)
        if begin<0: break
        if data.startswith(b'<!--',begin):
            end=data.find(b'-->',begin+4)
            if end<0: raise ValueError('Unclosed XML comment')
            at=end+3;continue
        if data.startswith(b'<![CDATA[',begin):
            end=data.find(b']]>',begin+9)
            if end<0: raise ValueError('Unclosed CDATA')
            at=end+3;continue
        if data.startswith(b'<?',begin):
            end=data.find(b'?>',begin+2)
            if end<0: raise ValueError('Unclosed XML instruction')
            at=end+2;continue
        if data.startswith(b'<!',begin): raise ValueError('DTD/entity declarations forbidden')
        pos=begin+1;quote=None
        while pos<len(data):
            ch=data[pos]
            if quote:
                if ch==quote: quote=None
            elif ch in (34,39): quote=ch
            elif ch==62: break
            elif ch==60: raise ValueError('Malformed XML tag')
            pos+=1
            if pos-begin>MAX_TEXT*2: raise ValueError('XML tag byte limit')
        if pos==len(data): raise ValueError('Unclosed XML tag')
        token=data[begin+1:pos];at=pos+1
        if token.startswith(b'/'):
            if not re.fullmatch(_NAME+rb'\s*',token[1:]): raise ValueError('Malformed XML close tag')
            out.append(b'<'+token+b'>');depth-=1
            if depth<0: raise ValueError('Malformed XML depth')
            continue
        empty=token.endswith(b'/');body=token[:-1] if empty else token
        match=re.match(_NAME,body)
        if not match: raise ValueError('Malformed XML element name')
        name=match[0];offset=match.end();attrs=[];seen=set()
        while offset<len(body):
            if not body[offset:].strip(): break
            attr=_ATTR.match(body,offset)
            if not attr: raise ValueError('Malformed XML attribute')
            aname,value=attr.groups();offset=attr.end()
            if aname in seen: raise ValueError('Duplicate XML attribute')
            seen.add(aname)
            local=name.split(b':')[-1]
            grid_attr=keep_grid and ((local in (b'row',b'c') and aname==b'r') or (local in (b'dimension',b'mergeCell',b'hyperlink') and aname==b'ref'))
            if aname==b'xmlns' or aname.startswith(b'xmlns:') or (local==b'table' and aname.split(b':')[-1] in (b'name',b'style-name',b'display')) or grid_attr:
                attrs.append(b' '+aname+b'='+value)
        out.append(b'<'+name+b''.join(attrs)+(b'/>' if empty else b'>'))
        nodes+=1
        if not empty: depth+=1
        if nodes>MAX_XML_NODES or depth>MAX_XML_DEPTH: raise ValueError('XML node/depth limit')
    if depth: raise ValueError('Unclosed XML structure')
    return b''.join(out)

def ods_metadata(content, guard):
    root=ET.fromstring(metadata_skeleton(content))
    if root.tag!=q('office','document-content'): raise ValueError('ODS content root unsupported')
    tables=root.findall('./office:body/office:spreadsheet/table:table',NS)
    if len(tables)!=sum(1 for _ in root.iter(q('table','table'))): raise ValueError('Nested/misplaced ODS tables unsupported')
    names=[t.get(q('table','name')) for t in tables]
    if not names or len(names)>MAX_SHEETS or any(not n for n in names) or len(names)!=len(set(names)):
        raise ValueError('ODS sheet metadata missing, duplicate or exceeds limit')
    guard(names)
    return names

def safe_xml(data):
    # Run bounded lexical checks before the full decoder, including styles.
    metadata_skeleton(data)
    return ET.fromstring(data)

def xlsx_metadata(data, guard):
    with checked_zip(data) as z:
        root=safe_xml(zip_member(z,'xl/workbook.xml'))
        ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        sheets=root.findall(ns+'sheets/'+ns+'sheet');names=[s.get('name') for s in sheets]
        if not names or any(not n for n in names) or len(names)>MAX_SHEETS or len(names)!=len(set(names)):
            raise ValueError('OOXML sheet metadata missing, duplicate or exceeds limit')
        guard(names)
        return names

def biff8_sheet_metadata(stream, with_offsets=False):
    """BOF/BOUNDSHEET only; SST and all sheet records remain undecoded."""
    offset=0;names=[];entries=[];first=True
    while offset+4<=len(stream):
        sid,size=struct.unpack_from('<HH',stream,offset);offset+=4
        if offset+size>len(stream): raise ValueError('Truncated BIFF record')
        payload=stream[offset:offset+size];offset+=size
        if first:
            first=False
            if sid!=0x0809 or size<4 or struct.unpack_from('<HH',payload)!=(0x0600,0x0005):
                raise ValueError('Only BIFF8 workbook-global metadata supported')
        if sid==0x002F: raise ValueError('Encrypted BIFF workbook unsupported')
        if sid==0x0085:
            if size<8: raise ValueError('Truncated BOUNDSHEET')
            count,flags=payload[6],payload[7];width=2 if flags&1 else 1
            if not count or flags not in (0,1) or 8+count*width!=size: raise ValueError('Invalid BOUNDSHEET name')
            name=payload[8:].decode('utf-16le' if width==2 else 'latin1')
            if payload[4] not in (0,1,2) or payload[5]!=0: raise ValueError('Unsupported BIFF sheet metadata/type')
            names.append(name)
            entries.append({'name':name,'offset':struct.unpack_from('<I',payload)[0]})
            if len(names)>MAX_SHEETS: raise ValueError('BIFF sheet count limit')
        if sid==0x000A:
            if not names or len(names)!=len(set(names)): raise ValueError('Missing/duplicate BOUNDSHEET metadata')
            return entries if with_offsets else names
    raise ValueError('No complete workbook-global EOF')

def grid_bound(rows, columns, label='spreadsheet'):
    if rows<0 or columns<0 or rows>MAX_ROWS or columns>MAX_COLUMNS or rows*columns>MAX_CELLS:
        raise ValueError(label+' row/column/rectangular cell limit')
    return rows*columns

def a1_coordinate(value, materialized=True):
    match=re.fullmatch(r'\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})',value or '')
    if not match: raise ValueError('Unsupported or malformed OOXML coordinate')
    column=0
    for ch in match[1]: column=column*26+ord(ch)-64
    row=int(match[2])
    if row>MAX_LOGICAL_ROWS or column>MAX_LOGICAL_COLUMNS: raise ValueError('Invalid OOXML logical coordinate')
    if materialized: grid_bound(row,column,'OOXML')
    return row,column

def a1_range(value, materialized=True):
    parts=(value or '').split(':')
    if len(parts) not in (1,2): raise ValueError('Unsupported OOXML range')
    start=a1_coordinate(parts[0],materialized);end=a1_coordinate(parts[-1],materialized)
    if start[0]>end[0] or start[1]>end[1]: raise ValueError('Inverted OOXML range')
    return start,end

def xlsx_grid_metadata(data, names):
    """Check declared AND actual extents before openpyxl constructs cells.

    XML grid skeletons retain only row/cell coordinates and range refs. Cell
    strings/formulas are discarded, and all sheet names were already cleared.
    """
    ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    ridns='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with checked_zip(data) as z:
        wb=safe_xml(zip_member(z,'xl/workbook.xml'));rels=safe_xml(zip_member(z,'xl/_rels/workbook.xml.rels'))
        links={}
        for rel in rels:
            ident=rel.get('Id')
            if not ident or ident in links: raise ValueError('Ambiguous OOXML workbook relationships')
            links[ident]=rel
        entries=[];total=0;total_expanded_ranges=0
        for sheet in wb.findall(ns+'sheets/'+ns+'sheet'):
            rel=links.get(sheet.get(ridns+'id'))
            if rel is None or rel.get('TargetMode')=='External' or not rel.get('Type','').endswith('/worksheet'):
                raise ValueError('Unsupported OOXML sheet relationship')
            target=rel.get('Target','')
            if '\\' in target or '://' in target or not target: raise ValueError('Unsafe OOXML sheet target')
            member=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if not member.startswith('xl/') or '..' in member.split('/'): raise ValueError('Unsafe OOXML sheet target')
            root=ET.fromstring(metadata_skeleton(zip_member(z,member),keep_grid=True))
            if root.tag!=ns+'worksheet': raise ValueError('Unsupported OOXML worksheet root')
            rows=0;columns=0;merges=[];occupied=set();previous_row=0;declared_dimension=None;row_metadata_extent=0
            dimensions=root.findall(ns+'dimension')
            if len(dimensions)>1: raise ValueError('Ambiguous OOXML dimensions')
            if dimensions:
                declared_dimension=dimensions[0].get('ref')
                # Normal openpyxl constructs cells from actual coordinates;
                # this advisory dimension can be stale and is not allocation.
                a1_range(declared_dimension,materialized=False)
            row_nodes=root.findall(ns+'sheetData/'+ns+'row')
            if len(row_nodes)!=sum(1 for _ in root.iter(ns+'row')): raise ValueError('Misplaced OOXML rows')
            seen_cells=set();cell_count=0
            for row in row_nodes:
                attr=row.get('r')
                if attr is not None and (not re.fullmatch(r'[1-9][0-9]{0,6}',attr)): raise ValueError('Invalid OOXML row index')
                rr=int(attr) if attr is not None else previous_row+1
                if rr<=previous_row: raise ValueError('Duplicate/unordered OOXML rows')
                if rr>MAX_LOGICAL_ROWS: raise ValueError('Invalid OOXML logical row index')
                previous_row=rr;row_metadata_extent=max(row_metadata_extent,rr)
                lastcol=0
                for cell in row.findall(ns+'c'):
                    cell_count+=1
                    cr,cc=a1_coordinate(cell.get('r')) if cell.get('r') is not None else (rr,lastcol+1)
                    if cr!=rr or (cr,cc) in seen_cells: raise ValueError('Ambiguous OOXML cell position')
                    seen_cells.add((cr,cc));lastcol=cc;rows=max(rows,cr);columns=max(columns,cc);grid_bound(rows,columns,'OOXML')
            if cell_count!=sum(1 for _ in root.iter(ns+'c')): raise ValueError('Misplaced OOXML cells')
            for tag in ('mergeCell','hyperlink'):
                for element in root.iter(ns+tag):
                    start,end=a1_range(element.get('ref'));rows=max(rows,end[0]);columns=max(columns,end[1]);grid_bound(rows,columns,'OOXML')
                    area=(end[0]-start[0]+1)*(end[1]-start[1]+1);total_expanded_ranges+=area
                    if total_expanded_ranges>MAX_CELLS: raise ValueError('OOXML aggregate merge/hyperlink expansion limit')
                    if tag=='mergeCell':
                        for rr in range(start[0],end[0]+1):
                            for cc in range(start[1],end[1]+1):
                                if (rr,cc) in occupied: raise ValueError('Overlapping OOXML merges')
                                occupied.add((rr,cc))
                        merges.append(element.get('ref'))
            total+=grid_bound(rows,columns,'OOXML')
            if total>MAX_CELLS: raise ValueError('OOXML total rectangular cell limit')
            entries.append({'name':sheet.get('name'),'member':member,'rows':rows,'columns':columns,'merges':merges,
                            'declared_dimension':declared_dimension,'row_metadata_extent':row_metadata_extent,
                            'allocation_basis':'actual cell, merge and hyperlink extents; dimension/row metadata preserved as diagnostics'})
        if [entry['name'] for entry in entries]!=names: raise ValueError('OOXML metadata mismatch')
        return entries

def biff_nonmaterializing_record(sid, payload):
    """Validate exactly four primary-documented records ignored by xlrd.

    No strings, UI objects or application-cache contents are interpreted.
    Rules/evidence are recorded in BIFF_COMPATIBILITY_EVIDENCE.md.
    """
    if sid not in BIFF_NONMATERIALIZING: raise ValueError('Unknown BIFF metadata record')
    size=len(payload)
    if size>MAX_BIFF_RECORD_BYTES: raise ValueError('BIFF metadata payload limit')
    if sid!=0x01C2:
        if size<12 or struct.unpack_from('<H',payload)[0]!=sid: raise ValueError('Invalid BIFF metadata FrtHeader.rt')
        if struct.unpack_from('<H',payload,2)[0]&3: raise ValueError('Invalid BIFF metadata FrtHeader flags')
    if sid==0x088B:
        if size!=16: raise ValueError('Invalid PLV record length')
        scale=struct.unpack_from('<H',payload,12)[0]
        if scale!=0 and not 10<=scale<=400: raise ValueError('Invalid PLV zoom scale')
    elif sid==0x0874:
        if size<14: raise ValueError('Truncated DropDownObjIds')
        count=struct.unpack_from('<H',payload,12)[0]
        if size!=14+count*2: raise ValueError('Invalid DropDownObjIds count/length')
    elif sid==0x089C:
        if size<38: raise ValueError('Truncated HeaderFooter')
        flags=struct.unpack_from('<H',payload,28)[0];counts=struct.unpack_from('<4H',payload,30)
        if any(count>255 for count in counts): raise ValueError('HeaderFooter string-count limit')
        if (not flags&1 and any(counts[:2])) or (not flags&2 and any(counts[2:])): raise ValueError('HeaderFooter flags/string-count mismatch')
        offset=38
        for count in counts:
            if not count: continue
            if offset+3>size: raise ValueError('Truncated HeaderFooter string framing')
            encoded_count=struct.unpack_from('<H',payload,offset)[0];string_flags=payload[offset+2];offset+=3
            if encoded_count!=count or string_flags&~1: raise ValueError('Invalid HeaderFooter string framing')
            offset+=count*(2 if string_flags&1 else 1)
            if offset>size: raise ValueError('Truncated HeaderFooter string bytes')
        if offset!=size: raise ValueError('Unexpected HeaderFooter trailing bytes')
    name,reference=BIFF_NONMATERIALIZING[sid]
    return {'record_id':f'0x{sid:04X}','record_name':name,'reference':reference,'payload_bytes':size,
            'payload_sha256':hashlib.sha256(payload).hexdigest(),
            'interpretation':'bounded non-materializing metadata; payload retained by source hash/offset, not interpreted as cell data'}

def biff8_grid_metadata(stream, entries, known_records):
    """Raw BIFF8 coordinates only, before xlrd SST/sheet value decoding.

    Unsupported record ids, nested substreams, invalid offsets/record lengths
    and ambiguous dimensions fail closed. The ids that can allocate cells in
    xlrd are all checked, including blank/multiple/formula records and merges.
    """
    offsets=[e['offset'] for e in entries]
    if len(offsets)!=len(set(offsets)) or any(o<0 or o+8>len(stream) for o in offsets): raise ValueError('Invalid BIFF worksheet offsets')
    ordered=sorted(offsets);limits={o:(ordered[i+1] if i+1<len(ordered) else len(stream)) for i,o in enumerate(ordered)}
    results=[];total=0;expanded_ranges=0;inert_count=0;inert_bytes=0
    single_sizes={0x0203:14,0x00FD:10,0x0204:9,0x00D6:9,0x027E:10,0x0205:8,0x0201:6,0x0006:22}
    for entry in entries:
        offset=entry['offset'];end=limits[offset];first=True;ended=False;dims=False;rows=0;columns=0;merges=[];occupied=set();had_cells=False;metadata_records=[];declared_dimensions=None;row_metadata_extent=0
        def extent(r,c):
            nonlocal rows,columns
            if r>65536 or c>256: raise ValueError('Invalid BIFF8 native coordinate')
            rows=max(rows,r);columns=max(columns,c);grid_bound(rows,columns,'BIFF8')
        def range8(payload, at=0, merge=False):
            nonlocal expanded_ranges
            if len(payload)<at+8: raise ValueError('Truncated BIFF range')
            r1,r2,c1,c2=struct.unpack_from('<HHHH',payload,at)
            if r1>r2 or c1>c2: raise ValueError('Inverted BIFF range')
            extent(r2+1,c2+1)
            expanded_ranges+=(r2-r1+1)*(c2-c1+1)
            if expanded_ranges>MAX_CELLS: raise ValueError('BIFF aggregate merge/hyperlink expansion limit')
            if merge:
                for rr in range(r1,r2+1):
                    for cc in range(c1,c2+1):
                        if (rr,cc) in occupied: raise ValueError('Overlapping BIFF merges')
                        occupied.add((rr,cc))
                merges.append((r1,r2+1,c1,c2+1))
        while offset+4<=end:
            record_offset=offset;sid,size=struct.unpack_from('<HH',stream,offset);offset+=4
            if offset+size>end: raise ValueError('Truncated/overlapping BIFF worksheet record')
            payload=stream[offset:offset+size];offset+=size
            if first:
                first=False
                if sid!=0x0809 or size<4 or struct.unpack_from('<HH',payload)!=(0x0600,0x0010): raise ValueError('Unsupported BIFF worksheet BOF')
                continue
            if sid==0x000A:
                if size or not dims: raise ValueError('Invalid BIFF worksheet EOF/dimensions')
                ended=True;break
            if sid in (0x0809,0x0409,0x0209,0x0009,0x0206,0x0406,0x0000,0x0001,0x0002,0x0003,0x0004,0x0005):
                raise ValueError('Unsupported/ambiguous BIFF worksheet structure')
            if sid in BIFF_NONMATERIALIZING:
                inert_count+=1;inert_bytes+=size
                if inert_count>MAX_INERT_BIFF_RECORDS or inert_bytes>MAX_INERT_BIFF_BYTES: raise ValueError('BIFF metadata aggregate limit')
                metadata_records.append(dict(biff_nonmaterializing_record(sid,payload),offset=record_offset))
                continue
            if sid not in known_records: raise ValueError('Unknown BIFF worksheet record: '+hex(sid))
            if sid==0x0200:
                if dims or had_cells or size!=14: raise ValueError('Ambiguous BIFF dimensions')
                r1,r2,c1,c2=struct.unpack_from('<IIHH',payload)
                if r1>r2 or c1>c2 or r2>65536 or c2>256: raise ValueError('Invalid BIFF dimensions')
                # xlrd stores these as _dimnrows/_dimncols diagnostics. Its
                # actual allocation is driven by cells and merged extents.
                dims=True;declared_dimensions={'first_row':r1,'past_last_row':r2,'first_column':c1,'past_last_column':c2}
            elif sid in single_sizes:
                if not dims or size<single_sizes[sid]: raise ValueError('Truncated/ambiguous BIFF cell')
                rr,cc=struct.unpack_from('<HH',payload);extent(rr+1,cc+1);had_cells=True
            elif sid in (0x00BD,0x00BE):
                if not dims or size<8: raise ValueError('Truncated BIFF multi-cell record')
                rr,c1=struct.unpack_from('<HH',payload);c2=struct.unpack_from('<H',payload,size-2)[0];width=6 if sid==0x00BD else 2
                if c1>c2 or size!=6+width*(c2-c1+1): raise ValueError('Invalid BIFF multi-cell span')
                extent(rr+1,c2+1);had_cells=True
            elif sid==0x0208:
                if size<16: raise ValueError('Truncated BIFF ROW')
                rr,c1,c2=struct.unpack_from('<HHH',payload)
                if c1>c2 or c2>256: raise ValueError('Invalid BIFF ROW span')
                row_metadata_extent=max(row_metadata_extent,rr+1)
            elif sid==0x00E5:
                if size<2: raise ValueError('Truncated BIFF merges')
                count=struct.unpack_from('<H',payload)[0]
                if size!=2+8*count: raise ValueError('Invalid BIFF merge count')
                for at in range(2,size,8): range8(payload,at,merge=True)
            elif sid==0x01B8: range8(payload)
            elif sid in (0x0221,0x04BC,0x0236):
                if size<6: raise ValueError('Truncated BIFF formula range')
                r1,r2,c1,c2=struct.unpack_from('<HHBB',payload)
                if r1>r2 or c1>c2: raise ValueError('Inverted BIFF formula range')
                extent(r2+1,c2+1)
        if not ended: raise ValueError('Incomplete BIFF worksheet EOF')
        total+=grid_bound(rows,columns,'BIFF8')
        if total>MAX_CELLS: raise ValueError('BIFF8 total rectangular cell limit')
        results.append(dict(entry,rows=rows,columns=columns,merges=merges,declared_dimensions=declared_dimensions,
                            row_metadata_extent=row_metadata_extent,nonmaterializing_records=metadata_records,
                            allocation_basis='actual cells, merges and hyperlink extents; DIMENSIONS/ROW diagnostics do not allocate the rectangular grid'))
    return results

def ods_external_formula(formula):
    """Conservative evidence only: never resolve or fetch any formula link."""
    # ODF external references have an IRI (which may be relative), a #, then
    # the sheet/range. Internal #REF! error references do not use this form.
    return bool(re.search(r'(?:[a-z]+://|file:)',formula,re.I) or
                re.search(r"\[(?:'(?:(?:'')|[^'])*'|[^\]\s#]+(?<!\.))#(?:\$|[A-Za-z_'\u0080-\uffff])",formula))

def positive_int(value, maximum, label):
    if value is None: return 1
    if len(value)>10 or not re.fullmatch(r'[0-9]+',value): raise ValueError('Invalid '+label)
    number=int(value)
    if not 1<=number<=maximum: raise ValueError(label+' limit exceeded')
    return number

def text_content(element):
    parts=[];length=0
    def append(value):
        nonlocal length
        if value:
            length+=len(value)
            if length>MAX_TEXT: raise ValueError('ODS cell text limit')
            parts.append(value)
    def visit(el):
        if el.tag==q('text','s'): append(' '*positive_int(el.get(q('text','c')),MAX_TEXT,'text repetition'))
        elif el.tag==q('text','tab'): append('\t')
        elif el.tag==q('text','line-break'): append('\n')
        else:
            append(el.text)
            for child in el:
                visit(child);append(child.tail)
    for i,p in enumerate(element.findall('text:p',NS)):
        if i: append('\n')
        visit(p)
    return ''.join(parts)

def ods_cell(el):
    attrs=dict(el.attrib);display=text_content(el);typ=el.get(q('office','value-type'));formula=el.get(q('table','formula'))
    native={'attributes':attrs,'value_type':typ,'display_text':display,'formula':formula}
    if formula and len(formula)>MAX_TEXT: raise ValueError('ODS formula length limit')
    value=None;has_cache=False;error=None
    try:
        if el.get(q('calcext','value-type'))=='error' or typ=='error': error='stored error value'
        elif typ in ('float','percentage','currency'):
            lexical=el.get(q('office','value'))
            if lexical is not None:
                if len(lexical)>256 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?',lexical): raise ValueError('invalid numeric value')
                number=Decimal(lexical)
                if not number.is_finite() or abs(number.adjusted())>308: raise ValueError('nonfinite/out-of-range numeric value')
                value=int(number) if number==number.to_integral_value() else float(number)
                if isinstance(value,float) and (not math.isfinite(value) or Decimal(str(value))!=number): value=format(number,'f')
                has_cache=True
        elif typ=='boolean':
            lexical=el.get(q('office','boolean-value'))
            if lexical is not None:
                if lexical not in ('true','false'): raise ValueError('invalid boolean value')
                value=lexical=='true';has_cache=True
        elif typ=='string':
            value=el.get(q('office','string-value'),display)
            if len(value)>MAX_TEXT: raise ValueError('ODS cell text limit')
            # A typed ODS empty string is a valid empty cache, unlike an
            # absent value type. Preserve that distinction.
            has_cache=True
        elif typ in ('date','time'):
            value=el.get(q('office',typ+'-value'))
            if value is not None:
                pattern=r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?' if typ=='date' else r'-?P(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?'
                if len(value)>MAX_TEXT or not re.fullmatch(pattern,value): raise ValueError('invalid '+typ+' value')
                has_cache=True
        elif typ is None:
            if not formula and display: value=display;has_cache=True
        else: error='unsupported ODS value type: '+str(typ)
    except (ValueError, InvalidOperation, OverflowError) as exc: error=str(exc)
    if formula and re.fullmatch(r'(?:#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!|SPILL!|CALC!)|Err:\s*\d+)',display.strip(),re.I): error='formula error cache'
    if typ is not None and not has_cache and error is None and not formula: error='declared cell type without value'
    if error: native['value_error']=error
    state=('formula-error' if formula else 'error') if error else 'cached-formula-value' if formula and has_cache else 'missing-formula-cache' if formula else 'literal' if has_cache else 'blank'
    return {'raw':formula if formula else value if not error else display or el.get(q('office','value')),
            'cached':value if formula and has_cache and not error else None,'state':state,'native':native,
            'storage_covered':el.tag==q('table','covered-table-cell')}

def provably_empty_cell(el):
    """Only content-free cell nodes qualify for sparse tail preservation.

    Value types (even empty strings), formulas, errors, merge declarations,
    annotations, text children and unknown attributes all prevent elision.
    Formatting-only attributes remain in the compressed range record.
    """
    return (el.tag==q('table','table-cell') and not len(el) and not (el.text or '').strip()
            and set(el.attrib)<={q('table','style-name'),q('table','number-columns-repeated')})

def read_ods(data, guard):
    with checked_zip(data) as z:
        content=zip_member(z,'content.xml')
        names=ods_metadata(content,guard)  # every sheet checked before decode
        manifest=safe_xml(zip_member(z,'META-INF/manifest.xml'))
        if any(el.tag.endswith('}encryption-data') for el in manifest.iter()): raise ValueError('Encrypted ODS unsupported')
        root=safe_xml(content)
        style_roots=[root]
        if 'styles.xml' in z.namelist(): style_roots.append(safe_xml(zip_member(z,'styles.xml')))
        styles={};default_display='true'
        for sr in style_roots:
            for st in sr.iter():
                if st.tag not in (q('style','style'),q('style','default-style')) or st.get(q('style','family'))!='table': continue
                props=st.find('style:table-properties',NS);display=props.get(q('table','display')) if props is not None else None
                if display not in (None,'true','false'): raise ValueError('Invalid ODS table display flag')
                if st.tag==q('style','default-style'): default_display=display or 'true';continue
                name=st.get(q('style','name'));record=(display,st.get(q('style','parent-style-name')))
                if name in styles and styles[name]!=record: raise ValueError('Conflicting ODS table styles')
                styles[name]=record
        def visibility(table):
            direct=table.get(q('table','display'))
            if direct not in (None,'true','false'): raise ValueError('Invalid ODS table display flag')
            style=table.get(q('table','style-name'));seen=set();display=direct
            while display is None and style:
                if style in seen: raise ValueError('Cyclic ODS table style')
                seen.add(style)
                if style not in styles: return 'unknown'
                display,style=styles[style]
            return 'hidden' if (display or default_display)=='false' else 'visible'
        tables=root.findall('./office:body/office:spreadsheet/table:table',NS)
        if names!=[t.get(q('table','name')) for t in tables]: raise ValueError('ODS metadata mismatch')
        sheets=[];total_cells=0
        for table in tables:
            rowplans=[];logical_rows=0;logical_cols=0;nrows=0;ncols=0;column_visibility=[];column_ranges=[]
            for column in table.iter(q('table','table-column')):
                repeat=positive_int(column.get(q('table','number-columns-repeated')),MAX_LOGICAL_COLUMNS,'column repetition')
                start=logical_cols+1;logical_cols+=repeat
                if logical_cols>MAX_LOGICAL_COLUMNS: raise ValueError('ODS logical column declaration limit')
                column_ranges.append({'start':start,'end':logical_cols,'attributes':dict(column.attrib)})
            for row in table.iter(q('table','table-row')):
                repeat=positive_int(row.get(q('table','number-rows-repeated')),MAX_LOGICAL_ROWS,'row repetition')
                start_row=logical_rows+1;logical_rows+=repeat
                if logical_rows>MAX_LOGICAL_ROWS: raise ValueError('ODS logical row limit')
                cells=[];width=0;used_width=0;used_height=0
                for cell in row:
                    if cell.tag not in (q('table','table-cell'),q('table','covered-table-cell')): raise ValueError('Unsupported ODS row child')
                    count=positive_int(cell.get(q('table','number-columns-repeated')),MAX_LOGICAL_COLUMNS,'cell repetition')
                    start_col=width+1
                    width+=count
                    if width>MAX_LOGICAL_COLUMNS: raise ValueError('ODS logical column limit')
                    empty=provably_empty_cell(cell)
                    if not empty:
                        span_cols=positive_int(cell.get(q('table','number-columns-spanned')),MAX_COLUMNS,'column span')
                        span_rows=positive_int(cell.get(q('table','number-rows-spanned')),MAX_ROWS,'row span')
                        used_width=max(used_width,width+span_cols-1);used_height=max(used_height,span_rows)
                    cells.append((cell,count,start_col,empty))
                if used_width:
                    nrows=max(nrows,logical_rows+used_height-1);ncols=max(ncols,used_width)
                logical_cols=max(logical_cols,width)
                # Limits apply to original coordinates, so a huge empty gap
                # followed by any value/formula cannot evade them.
                if nrows>MAX_ROWS or ncols>MAX_COLUMNS: raise ValueError('ODS materialized row/column limit')
                rowplans.append((row,repeat,cells,start_row))
            if nrows>logical_rows or ncols>logical_cols: raise ValueError('ODS merge outside stored grid')
            for cr in column_ranges:
                count=max(0,min(ncols,cr['end'])-cr['start']+1)
                column_visibility.extend([cr['attributes'].get(q('table','visibility'),'visible')]*count)
            total_cells+=nrows*ncols
            if total_cells>MAX_CELLS: raise ValueError('ODS expanded rectangular cell limit')
            rows=[];merges=[];covered={};row_visibility=[];blank_ranges=[];row_ranges=[]
            for row,repeat,cells,start_row in rowplans:
                end_row=start_row+repeat-1;active_repeat=max(0,min(nrows,end_row)-start_row+1)
                row_ranges.append({'start':start_row,'end':end_row,'attributes':dict(row.attrib)})
                for el,count,start_col,empty in cells:
                    end_col=start_col+count-1
                    # Record exact elided rectangles, including style names.
                    # There is no omission of any formula/value/covered cell.
                    if end_row>nrows:
                        if not empty: raise ValueError('Nonempty ODS tail cannot be elided')
                        blank_ranges.append({'rows':[max(start_row,nrows+1),end_row],'columns':[start_col,end_col],'cell_attributes':dict(el.attrib),'reason':'proven_empty_trailing_rows'})
                    if start_row<=nrows and end_col>ncols:
                        if not empty: raise ValueError('Nonempty ODS tail cannot be elided')
                        blank_ranges.append({'rows':[start_row,min(end_row,nrows)],'columns':[max(start_col,ncols+1),end_col],'cell_attributes':dict(el.attrib),'reason':'proven_empty_trailing_columns'})
                for _ in range(active_repeat):
                    rr=len(rows)+1;output=[];row_visibility.append(row.get(q('table','visibility'),'visible'))
                    for el,count,start_col,empty in cells:
                        count=max(0,min(ncols,start_col+count-1)-start_col+1)
                        if not count: continue
                        value=ods_cell(el)
                        col_span=positive_int(el.get(q('table','number-columns-spanned')),MAX_COLUMNS,'column span')
                        row_span=positive_int(el.get(q('table','number-rows-spanned')),MAX_ROWS,'row span')
                        for _ in range(count):
                            cc=len(output)+1;co=f'{colname(cc)}{rr}';cell=dict(value,cell=co)
                            output.append(cell)
                            if col_span>1 or row_span>1:
                                if value['storage_covered'] or cc+col_span-1>ncols or rr+row_span-1>nrows: raise ValueError('ODS merge outside stored grid')
                                merges.append(f'{co}:{colname(cc+col_span-1)}{rr+row_span-1}')
                                for mr in range(rr,rr+row_span):
                                    for mc in range(cc,cc+col_span):
                                        if (mr,mc) in covered: raise ValueError('Overlapping ODS merges')
                                        covered[mr,mc]=co
                    while len(output)<ncols: output.append({'cell':f'{colname(len(output)+1)}{rr}','raw':None,'cached':None,'state':'blank','native':None,'storage_covered':False})
                    rows.append(output)
            conflicts=[]
            for rr,row in enumerate(rows,1):
                for cc,cell in enumerate(row,1):
                    anchor=covered.get((rr,cc));is_covered=anchor is not None and anchor!=cell['cell']
                    if cell['storage_covered'] and not is_covered: raise ValueError('Orphan ODS covered cell')
                    if is_covered:
                        if cell['state']!='blank': conflicts.append({'cell':cell['cell'],'anchor':anchor,'native':cell['native'],'raw':cell['raw'],'cached':cell['cached'],'original_state':cell['state']})
                        cell.update(state='merged-covered',anchor=anchor)
                    else: cell['anchor']=None
            sheets.append({'name':table.get(q('table','name')),'visibility':visibility(table),'dimensions':f'A1:{colname(ncols)}{nrows}' if nrows and ncols else 'A1:A1',
                           'merges':merges,'covered_conflicts':conflicts,'rows':rows,'row_visibility':row_visibility,'column_visibility':column_visibility,
                           'stored_grid':{'rows':logical_rows,'columns':logical_cols,'dimensions':f'A1:{colname(logical_cols)}{logical_rows}' if logical_rows and logical_cols else 'A1:A1','materialized_rows':nrows,'materialized_columns':ncols},
                           'row_storage_ranges':row_ranges,'column_storage_ranges':column_ranges,'compressed_blank_ranges':blank_ranges})
        external=any(el.get(q('xlink','href')) and not el.get(q('xlink','href')).startswith('#') for sr in style_roots for el in sr.iter())
        external=external or any(ods_external_formula(el.get(q('table','formula'),'')) for el in root.iter())
        return {'sheets':sheets,'external_links_present':bool(external),'limits':{'expanded_cells':total_cells,'max_cells':MAX_CELLS,'max_rows':MAX_ROWS,'max_columns':MAX_COLUMNS,'max_zip_decompressed_bytes':MAX_ZIP_BYTES},
                'limitations':['ODS formulas and saved typed caches preserved; formulas never evaluated or recalculated.',
                               'Provably empty trailing repeated grid regions are preserved as coordinate/attribute ranges, not expanded into individual cells; positions within the materialized grid never shift.',
                               'ODS styles used only for sheet visibility; rendering, drawings, annotations and number-format display are not material evidence.',
                               'Source metadata clearance and format readability do not establish contract adoption/version/scope.']}
