"""Documented inert BIFF metadata and advisory-extent counterexamples."""
import hashlib,io,struct,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import cps
import source_formats as f
from test_container_limits import rec,sheet_stream,number_record,full_biff,xlsx
ROOT=Path(__file__).resolve().parent
def frt(sid): return struct.pack('<HH',sid,0)+b'\0'*8
def headerfooter(text=b''):
    return frt(0x089C)+b'\0'*16+struct.pack('<H4H',1 if text else 0,len(text),0,0,0)+(struct.pack('<HB',len(text),0)+text if text else b'')
def plv(scale=100): return frt(0x088B)+struct.pack('<HH',scale,0)
def dropdown(ids=(1,2)):
    return frt(0x0874)+struct.pack('<H',len(ids))+b''.join(struct.pack('<H',v) for v in ids)
def inspect(records,rows=1,columns=1):
    from xlrd.biffh import biff_rec_name_dict
    return f.biff8_grid_metadata(sheet_stream(records,rows,columns),[{'name':'detail','offset':0}],set(biff_rec_name_dict))[0]

class MetadataCompatibilityTests(unittest.TestCase):
    def test_all_four_documented_types_are_traced_without_grid_changes(self):
        payloads={0x089C:headerfooter(),0x088B:plv(),0x0874:dropdown(),0x01C2:b'opaque application cache'}
        result=inspect([number_record(0,0)]+[rec(sid,payload) for sid,payload in payloads.items()])
        self.assertEqual((result['rows'],result['columns']),(1,1))
        self.assertEqual(len(result['nonmaterializing_records']),4)
        for item,(sid,payload) in zip(result['nonmaterializing_records'],payloads.items()):
            self.assertEqual(item['record_id'],f'0x{sid:04X}')
            self.assertEqual(item['payload_sha256'],hashlib.sha256(payload).hexdigest());self.assertGreater(item['offset'],0)
            self.assertNotIn('value',item);self.assertNotIn('text',item)
    def test_opaque_cache_cannot_create_cells(self):
        payload=number_record(65535,255)+b'NOT A REAL CELL'
        result=inspect([number_record(0,0),rec(0x01C2,payload)])
        self.assertEqual((result['rows'],result['columns']),(1,1))
    def test_unknown_type_not_allowed_by_matching_payload(self):
        for sid in (0x089D,0x088C,0x01C3,0x0875,0xFFFF):
            with self.assertRaisesRegex(ValueError,'Unknown'): inspect([rec(sid,headerfooter())])
    def test_frt_type_and_flags_must_match(self):
        for sid,payload in ((0x088B,plv()),(0x0874,dropdown()),(0x089C,headerfooter())):
            bad=b'\x00\x00'+payload[2:]
            with self.assertRaisesRegex(ValueError,'FrtHeader.rt'): inspect([rec(sid,bad)])
            bad=payload[:2]+b'\x01\x00'+payload[4:]
            with self.assertRaisesRegex(ValueError,'flags'): inspect([rec(sid,bad)])
    def test_plv_length_and_scale_bound(self):
        for value in (plv()[:-1],plv()+b'x',plv(401),plv(9)):
            with self.assertRaises(ValueError): inspect([rec(0x088B,value)])
        for scale in (0,10,400): self.assertEqual(len(inspect([rec(0x088B,plv(scale))])['nonmaterializing_records']),1)
    def test_dropdown_exact_identifier_count(self):
        for value in (dropdown()[:-1],dropdown()+b'x',frt(0x0874),frt(0x0874)+struct.pack('<H',65535)):
            with self.assertRaises(ValueError): inspect([rec(0x0874,value)])
    def test_headerfooter_framing_not_text_decoding(self):
        result=inspect([rec(0x089C,headerfooter(b'\xffopaque\xfe'))])
        self.assertEqual(len(result['nonmaterializing_records']),1)
        for value in (headerfooter()[:-1],headerfooter()+b'x',headerfooter(b'abc')[:-1],headerfooter(b'a')[:30]+struct.pack('<H',256)+headerfooter(b'a')[32:]):
            with self.assertRaises(ValueError): inspect([rec(0x089C,value)])
    def test_metadata_record_and_aggregate_bounds(self):
        with self.assertRaisesRegex(ValueError,'payload limit'): inspect([rec(0x01C2,b'x'*8225)])
        with patch.object(f,'MAX_INERT_BIFF_RECORDS',2):
            with self.assertRaisesRegex(ValueError,'aggregate'): inspect([rec(0x088B,plv())]*3)
        with patch.object(f,'MAX_INERT_BIFF_BYTES',31):
            with self.assertRaisesRegex(ValueError,'aggregate'): inspect([rec(0x088B,plv())]*2)
    def test_allowance_does_not_bypass_actual_cell_limit(self):
        with patch.object(f,'MAX_ROWS',2):
            with self.assertRaisesRegex(ValueError,'limit'): inspect([rec(0x089C,headerfooter()),number_record(2,0)])
    def test_invalid_metadata_rejected_before_xlrd_decoder(self):
        import xlrd
        with patch('xlrd.compdoc.CompDoc') as container,patch.object(xlrd,'open_workbook',side_effect=AssertionError('must not load')) as loader:
            container.return_value.get_named_stream.return_value=full_biff(sheet_stream([rec(0x0874,dropdown()[:-1])]))
            with self.assertRaises(ValueError): cps.read_xls({'path':'unused'},_data=f.OLE_MAGIC)
            loader.assert_not_called()

class AdvisoryExtentTests(unittest.TestCase):
    def test_fullwidth_ok_paths_and_sheets_block_before_loader(self):
        for name in ('工程ＯＫ.xlsx','ＯＫ版本.xls','原材料清單.ods'):
            with self.assertRaisesRegex(ValueError,'Forbidden'): cps.reject_source(Path(name))
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            p=Path(temp)/'contract.xlsx';book=Workbook();book.active.title='ＯＫ';book.active['A1']='must not decode';book.save(p);book.close()
            with patch('openpyxl.load_workbook',side_effect=AssertionError('must not load')) as loader:
                with self.assertRaisesRegex(ValueError,'Forbidden embedded'): cps.read_xlsx({'path':str(p)})
                loader.assert_not_called()
    def test_ooxml_large_advisory_dimension_does_not_allocate_cells(self):
        data=xlsx({'A1':'small actual source'},dimension='A1:XFD1048576')
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            p=Path(temp)/'contract.xlsx';p.write_bytes(data)
            with patch.object(f,'MAX_ROWS',2),patch.object(f,'MAX_COLUMNS',2),patch.object(f,'MAX_CELLS',2): result=cps.read_xlsx({'path':str(p)})
        self.assertEqual(result['sheets'][0]['dimensions'],'A1:A1')
        self.assertEqual(result['grid_preflight'][0]['declared_dimension'],'A1:XFD1048576')
        self.assertEqual((result['grid_preflight'][0]['rows'],result['grid_preflight'][0]['columns']),(1,1))
    def test_ooxml_bare_row_metadata_stays_diagnostic(self):
        data=xlsx({'A1':'small source'})
        with zipfile.ZipFile(io.BytesIO(data)) as z: members={n:z.read(n) for n in z.namelist()}
        members['xl/worksheets/sheet1.xml']=members['xl/worksheets/sheet1.xml'].replace(b'</sheetData>',b'<row r="1048576" hidden="1"></row></sheetData>')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for name,value in members.items(): z.writestr(name,value)
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            p=Path(temp)/'contract.xlsx';p.write_bytes(stream.getvalue())
            with patch.object(f,'MAX_ROWS',2): result=cps.read_xlsx({'path':str(p)})
        self.assertEqual(len(result['sheets'][0]['rows']),1);self.assertEqual(result['grid_preflight'][0]['row_metadata_extent'],1048576)
    def test_biff_overstated_dimensions_do_not_allocate_cells(self):
        with patch.object(f,'MAX_ROWS',2),patch.object(f,'MAX_COLUMNS',2),patch.object(f,'MAX_CELLS',2):
            result=inspect([number_record(0,0)],rows=65536,columns=256)
        self.assertEqual((result['rows'],result['columns']),(1,1));self.assertEqual(result['declared_dimensions']['past_last_row'],65536)
    def test_biff_actual_merge_still_blocks_with_small_advisory_dimensions(self):
        merge=rec(0x00E5,struct.pack('<HHHHH',1,0,2,0,2))
        with patch.object(f,'MAX_CELLS',8):
            with self.assertRaisesRegex(ValueError,'limit'): inspect([merge],rows=1,columns=1)

if __name__=='__main__':unittest.main(verbosity=2)
