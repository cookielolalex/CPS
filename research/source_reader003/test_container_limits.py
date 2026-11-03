"""Synthetic pre-loader regressions for audit002 format-boundary findings."""
from pathlib import Path
import io
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import cps
import source_formats as f
from test_source_formats import package,table,row,cell

ROOT=Path(__file__).resolve().parent

def xlsx(cells,merge=None,sheets=1,dimension=None):
    from openpyxl import Workbook
    stream=io.BytesIO();book=Workbook();book.active.title='detail'
    for index in range(sheets):
        sheet=book.active if index==0 else book.create_sheet('detail'+str(index))
        for coordinate,value in cells.items(): sheet[coordinate]=value
        if merge: sheet.merge_cells(merge)
    book.save(stream);book.close();data=stream.getvalue()
    if dimension is not None:
        import re
        with zipfile.ZipFile(io.BytesIO(data)) as z: members={n:z.read(n) for n in z.namelist()}
        for name,value in members.items():
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                members[name]=re.sub(rb'<dimension[^>]*/>',b'<dimension ref="'+dimension.encode()+b'"/>',value)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for name,value in members.items(): z.writestr(name,value)
        data=stream.getvalue()
    return data

def rec(kind,data=b''): return struct.pack('<HH',kind,len(data))+data
def sheet_stream(records,rows=2,columns=2):
    return rec(0x0809,struct.pack('<HH',0x0600,0x0010))+rec(0x0200,struct.pack('<IIHHH',0,rows,0,columns,0))+b''.join(records)+rec(0x000A)
def number_record(rr,cc): return rec(0x0203,struct.pack('<HHHd',rr,cc,0,1.0))
def full_biff(sheet):
    name='detail';encoded=name.encode('utf-16le')
    start=rec(0x0809,struct.pack('<HH',0x0600,0x0005))
    size=len(start)+4+8+len(encoded)+4
    bounds=rec(0x0085,struct.pack('<IBBBB',size,0,0,len(name),1)+encoded)
    return start+bounds+rec(0x000A)+sheet

class OOXMLPreflightTests(unittest.TestCase):
    def blocked_before_loader(self,data,**limits):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'contract.xlsx';path.write_bytes(data)
            from contextlib import ExitStack
            with ExitStack() as stack:
                for key,value in limits.items(): stack.enter_context(patch.object(f,key,value))
                loader=stack.enter_context(patch('openpyxl.load_workbook',side_effect=AssertionError('loader must not run')))
                with self.assertRaises(ValueError): cps.read_xlsx({'path':str(path)})
                loader.assert_not_called()
    def test_row_limit_before_openpyxl(self): self.blocked_before_loader(xlsx({'A3':'late'}),MAX_ROWS=2)
    def test_column_limit_before_openpyxl(self): self.blocked_before_loader(xlsx({'C1':'late'}),MAX_COLUMNS=2)
    def test_rectangular_limit_not_just_nonblank_cells(self): self.blocked_before_loader(xlsx({'B2':'only one stored cell'}),MAX_CELLS=3)
    def test_misleading_small_dimension_does_not_hide_far_cell(self): self.blocked_before_loader(xlsx({'A3':'late'},dimension='A1'),MAX_ROWS=2)
    def test_invalid_logical_dimension_still_blocked(self): self.blocked_before_loader(xlsx({'A1':'value'},dimension='A1:XFE1048576'))
    def test_merge_extent_before_openpyxl_construction(self): self.blocked_before_loader(xlsx({'A1':'anchor'},merge='A1:C3'),MAX_CELLS=8)
    def test_actual_merge_extent_with_false_small_dimension(self): self.blocked_before_loader(xlsx({'A1':'anchor'},merge='A1:C3',dimension='A1'),MAX_ROWS=2)
    def test_total_grid_across_sheets(self): self.blocked_before_loader(xlsx({'B2':'value'},sheets=2),MAX_CELLS=7)
    def test_bounded_two_sheet_grid_and_cached_cells_still_read(self):
        data=xlsx({'A1':'a','B2':3},sheets=2)
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'contract.xlsx';path.write_bytes(data)
            with patch.object(f,'MAX_CELLS',8): result=cps.read_xlsx({'path':str(path)})
            self.assertEqual(len(result['sheets']),2);self.assertEqual(result['sheets'][1]['rows'][1][1]['raw'],3)
            self.assertEqual(result['grid_preflight'][1]['rows'],2)
    def test_hyperlink_range_must_be_bounded_before_bind(self):
        data=xlsx({'A1':'value'})
        with zipfile.ZipFile(io.BytesIO(data)) as z: members={n:z.read(n) for n in z.namelist()}
        members['xl/worksheets/sheet1.xml']=members['xl/worksheets/sheet1.xml'].replace(b'</worksheet>',b'<hyperlinks><hyperlink ref="A1:C3" location="A1"/></hyperlinks></worksheet>')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for name,value in members.items(): z.writestr(name,value)
        self.blocked_before_loader(stream.getvalue(),MAX_CELLS=8)

class BIFFPreflightTests(unittest.TestCase):
    def inspect(self,stream):
        from xlrd.biffh import biff_rec_name_dict
        return f.biff8_grid_metadata(stream,[{'name':'detail','offset':0}],set(biff_rec_name_dict))
    def test_valid_biff_dimensions_and_actual_cells(self):
        value=self.inspect(sheet_stream([number_record(1,1)]))
        self.assertEqual((value[0]['rows'],value[0]['columns']),(2,2))
    def test_dimensions_before_xlrd_loader(self):
        import xlrd
        with patch('xlrd.compdoc.CompDoc') as container,patch.object(xlrd,'open_workbook',side_effect=AssertionError('Must not decode SST/sheets')) as loader,patch.object(f,'MAX_ROWS',2):
            container.return_value.get_named_stream.return_value=full_biff(sheet_stream([],rows=65537))
            with self.assertRaisesRegex(ValueError,'dimensions'): cps.read_xls({'path':'unused'},_data=f.OLE_MAGIC)
            loader.assert_not_called()
    def test_underdeclared_dimensions_cannot_hide_actual_far_cell(self):
        with patch.object(f,'MAX_ROWS',2):
            with self.assertRaisesRegex(ValueError,'limit'): self.inspect(sheet_stream([number_record(2,0)],rows=1,columns=1))
    def test_row_metadata_preserved_without_fictitious_allocation(self):
        row_record=rec(0x0208,struct.pack('<HHH',2,0,1)+b'\x00'*10)
        with patch.object(f,'MAX_ROWS',2):
            result=self.inspect(sheet_stream([row_record,number_record(0,0)],rows=1,columns=1))[0]
        self.assertEqual(result['rows'],1);self.assertEqual(result['row_metadata_extent'],3)
    def test_merge_bounds_precede_expansion(self):
        merge=rec(0x00E5,struct.pack('<HHHHH',1,0,2,0,2))
        with patch.object(f,'MAX_CELLS',8):
            with self.assertRaisesRegex(ValueError,'limit'): self.inspect(sheet_stream([merge],rows=1,columns=1))
    def test_multicell_bounds_and_malformed_counts(self):
        good=rec(0x00BE,struct.pack('<HHHHHH',0,0,0,0,0,2))
        with patch.object(f,'MAX_COLUMNS',2):
            with self.assertRaisesRegex(ValueError,'limit'): self.inspect(sheet_stream([good],rows=1,columns=1))
        bad=rec(0x00BE,struct.pack('<HHHH',0,0,0,2))
        with self.assertRaisesRegex(ValueError,'span'): self.inspect(sheet_stream([bad]))
    def test_unknown_nested_and_ambiguous_structures_fail_closed(self):
        for value in (rec(0xFFFF,b'unsupported'),rec(0x0809,struct.pack('<HH',0x0600,0x0020)),rec(0x0200,struct.pack('<IIHHH',0,2,0,2,0))):
            with self.assertRaises(ValueError): self.inspect(sheet_stream([value]))
    def test_total_grid_across_biff_sheets(self):
        first=sheet_stream([number_record(1,1)]);second=sheet_stream([number_record(1,1)]);stream=first+second
        from xlrd.biffh import biff_rec_name_dict
        with patch.object(f,'MAX_CELLS',7):
            with self.assertRaisesRegex(ValueError,'total'): f.biff8_grid_metadata(stream,[{'name':'one','offset':0},{'name':'two','offset':len(first)}],set(biff_rec_name_dict))
    def test_biff_offsets_and_truncation_fail_closed(self):
        from xlrd.biffh import biff_rec_name_dict
        for entries in ([{'name':'one','offset':99999}],[{'name':'one','offset':0},{'name':'two','offset':0}]):
            with self.assertRaises(ValueError): f.biff8_grid_metadata(sheet_stream([]),entries,set(biff_rec_name_dict))
        with self.assertRaises(ValueError): self.inspect(sheet_stream([])[:-4])

class RelativeExternalTests(unittest.TestCase):
    def test_relative_quoted_and_unquoted_formula_links_recorded(self):
        for formula in ("of:=['other.ods'#$Sheet1.A1]","of:=['../other.ods'#$'Sheet 1'.A1]","of:=[other.ods#Sheet1.A1]","of:=['file:///other.ods'#$Sheet1.A1]"):
            data=package(table([row(cell('1',f'table:formula="{formula}" office:value-type="float" office:value="1"'))]))
            result=f.read_ods(data,cps.assert_contract_sheet_names)
            self.assertIs(result['external_links_present'],True)
            self.assertEqual(result['sheets'][0]['rows'][0][0]['raw'],formula)
    def test_internal_cell_and_ref_error_not_external_document(self):
        for formula in ('of:=[.A1]','of:=[Sheet1.A1]','of:=IF([.F773]<>[標單詳細表.#REF!];1;0)'):
            self.assertFalse(f.ods_external_formula(formula))

if __name__=='__main__': unittest.main(verbosity=2)
