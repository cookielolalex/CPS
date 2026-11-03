"""Source-only, synthetic fixtures: container boundary and ODS meaning loss.

No target, historical answer, gold or evaluator access.
"""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from xml.sax.saxutils import escape
import cps
import source_formats as f

ROOT=Path(__file__).resolve().parent
RUN=ROOT.parents[1]
sys.path.insert(0,str(RUN/'deps'))
NS=' '.join(f'xmlns:{prefix}="{uri}"' for prefix,uri in f.NS.items())
def cell(text='', attrs='', covered=False):
    tag='covered-table-cell' if covered else 'table-cell'
    return f'<table:{tag} {attrs}><text:p>{escape(str(text))}</text:p></table:{tag}>'
def string(text): return cell(text,'office:value-type="string"')
def number(value): return cell(str(value),f'office:value-type="float" office:value="{value}"')
def row(*cells, attrs=''): return f'<table:table-row {attrs}>'+''.join(cells)+'</table:table-row>'
def table(rows, name='契約詳細表', attrs=''): return f'<table:table table:name="{name}" {attrs}>'+''.join(rows)+'</table:table>'
def content(tables, styles=''):
    return f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {NS}><office:automatic-styles>{styles}</office:automatic-styles><office:body><office:spreadsheet>{tables}</office:spreadsheet></office:body></office:document-content>'.encode()
def package(tables='', styles='', extra=None, xml=None, mime=f.ODS_MIME):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('mimetype',mime,compress_type=zipfile.ZIP_STORED)
        z.writestr('content.xml',content(tables,styles) if xml is None else xml)
        z.writestr('META-INF/manifest.xml','<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>')
        for name,value in (extra or {}).items(): z.writestr(name,value)
    return stream.getvalue()
def read(data): return f.read_ods(data,cps.assert_contract_sheet_names)
def biff(names):
    def rec(kind,payload=b''): return struct.pack('<HH',kind,len(payload))+payload
    records=[rec(0x0809,struct.pack('<HH',0x0600,0x0005))]
    for name in names:
        encoded=name.encode('utf-16le');records.append(rec(0x0085,struct.pack('<IBBBB',0,0,0,len(name),1)+encoded))
    # Shared-string data intentionally invalid: metadata parser must skip it.
    return b''.join(records)+rec(0x00FC,b'\xff\xfeSST SENTINEL')+rec(0x000A)

class ContainerTests(unittest.TestCase):
    def test_actual_ods_misnamed_xls_and_source_hash(self):
        data=package(table([row(string('header'))]))
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'contract.xls';path.write_bytes(data)
            source={'path':str(path),'sha256':cps.sha(path),'role':'contract'}
            result=cps.read_source(source)
            self.assertEqual(result['detected_container'],'ODS_ZIP')
            self.assertEqual(result['sheets'][0]['rows'][0][0]['raw'],'header')
            source['sha256']='0'*64
            with patch('source_formats.read_ods',side_effect=AssertionError('hash must gate decoder')) as decoder:
                with self.assertRaisesRegex(ValueError,'hash mismatch'): cps.read_source(source)
                decoder.assert_not_called()
    def test_actual_ooxml_misnamed_xls(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'contract.xls';w=Workbook();w.active.title='契約';w.active['A1']='visible';w.save(path);w.close()
            result=cps.read_source({'path':str(path),'sha256':cps.sha(path),'role':'contract'})
            self.assertEqual(result['detected_container'],'OOXML_ZIP')
            self.assertEqual(result['sheets'][0]['rows'][0][0]['raw'],'visible')
    def test_unknown_and_ambiguous_containers_fail_closed(self):
        for data in (b'not spreadsheet',package(mime=b'application/unknown'),package(extra={'[Content_Types].xml':'x','xl/workbook.xml':'x','xl/_rels/workbook.xml.rels':'x'})):
            with self.assertRaises(ValueError): f.detect_container(data)
    def test_duplicate_members_and_unsafe_paths_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'): f.detect_container(package(extra={'../outside.xml':'x'}))
        stream=io.BytesIO(package())
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(stream,'a') as z: z.writestr('content.xml','x')
        with self.assertRaisesRegex(ValueError,'duplicate'): f.detect_container(stream.getvalue())
    def test_compressed_payload_bound_before_xml(self):
        data=package(xml=b'x'*4096)
        with patch.object(f,'MAX_XML_BYTES',2048):
            with self.assertRaisesRegex(ValueError,'byte limit'): read(data)
        with patch.object(f,'MAX_ZIP_BYTES',2048):
            with self.assertRaisesRegex(ValueError,'decompressed'): read(data)
    def test_source_changed_after_snapshot_rejected(self):
        data=package(table([row(string('one'))]))
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'contract.ods';path.write_bytes(data)
            source={'path':str(path),'sha256':cps.sha(path),'role':'contract'}
            original=f.read_ods
            def changed(snapshot,guard):
                path.write_bytes(package(table([row(string('two'))])))
                return original(snapshot,guard)
            with patch.object(f,'read_ods',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed while reading'): cps.read_source(source)
    def test_later_stage_filename_variants(self):
        for name in ('鈑金.xlsx','電機施工圖.xls','生產表.ods','領料單.xls','原材料清單.xlsx','OK1.xlsx','copy_OK_2.xls'):
            with self.assertRaisesRegex(ValueError,'Forbidden'): cps.reject_source(Path(name))

class MetadataBoundaryTests(unittest.TestCase):
    def test_forbidden_last_sheet_precedes_all_cell_string_decoding(self):
        # The first cell is invalid UTF-8 and has an undefined XML entity.
        # A full XML decoder would fail before finding the final sheet.
        xml=content(table([row(string('SENTINEL'))],name='first')+table([],name='未&#x586B;'))
        xml=xml.replace(b'SENTINEL',b'\xff&undefined;')
        with patch.object(f,'ods_cell',side_effect=AssertionError('Must never decode')) as decoder:
            with self.assertRaisesRegex(ValueError,'Forbidden embedded'): read(package(xml=xml))
            decoder.assert_not_called()
    def test_all_forbidden_sheet_forms_checked(self):
        for name in ('未填','已填','OK','OK表','OK_2','電機施工圖','電機','板金','鈑金','原材料清單','領料單','生產','製造'):
            with self.assertRaisesRegex(ValueError,'Forbidden embedded',msg=name): read(package(table([],name=name)))
    def test_namespace_alias_and_nested_rebinding_not_bypass(self):
        xml=content(table([],name='未填')).replace(b'table:table ',b't:table xmlns:t="'+f.NS['table'].encode()+b'" ').replace(b'</table:table>',b'</t:table>')
        with self.assertRaisesRegex(ValueError,'Forbidden embedded'): read(package(xml=xml))
    def test_nested_duplicate_and_missing_tables_rejected(self):
        for tables in (table([table([],name='nested')]),table([],name='same')+table([],name='same'),''):
            with self.assertRaises(ValueError): read(package(tables))
    def test_metadata_quote_aware_and_cdata_text_not_table(self):
        xml=content(table([row(string('retained'))],name='detail > 1'))
        xml=xml.replace(b'retained',b'<![CDATA[<table:table table:name="\xe6\x9c\xaa\xe5\xa1\xab"/>]]>')
        result=read(package(xml=xml))
        self.assertEqual(result['sheets'][0]['name'],'detail > 1')
        self.assertIn('未填',result['sheets'][0]['rows'][0][0]['raw'])
    def test_dtd_and_entities_rejected(self):
        xml=content(table([row(string('x'))])).replace(b'<office:document-content',b'<!DOCTYPE x [<!ENTITY leaked SYSTEM "file:///secret">]><office:document-content',1)
        with self.assertRaisesRegex(ValueError,'DTD/entity'): read(package(xml=xml))
    def test_xml_depth_nodes_encoding_and_malformed_guard(self):
        xml=content(table([row(string('x'))]))
        with patch.object(f,'MAX_XML_NODES',5):
            with self.assertRaisesRegex(ValueError,'node/depth'): read(package(xml=xml))
        with patch.object(f,'MAX_XML_DEPTH',4):
            with self.assertRaisesRegex(ValueError,'node/depth'): read(package(xml=xml))
        for bad in (xml.replace(b'UTF-8',b'UTF-16'),xml.replace(b'</text:p>',b'</bad>'),xml.replace(b'office:value-type="string"',b'office:value-type="string" office:value-type="string"')):
            with self.assertRaises(Exception): read(package(xml=bad))
    def test_biff8_only_metadata_skips_sst(self):
        self.assertEqual(f.biff8_sheet_metadata(biff(['契約','明細'])),['契約','明細'])
        for raw in (biff(['契約'])[:-4],biff(['契約']).replace(b'\x00\x06\x05\x00',b'\x00\x05\x05\x00',1)):
            with self.assertRaises(ValueError): f.biff8_sheet_metadata(raw)
    def test_biff_forbidden_late_sheet_blocks_xlrd_loader(self):
        import xlrd
        with patch('xlrd.compdoc.CompDoc') as container, patch.object(xlrd,'open_workbook',side_effect=AssertionError('Must not decode SST')) as loader:
            container.return_value.get_named_stream.return_value=biff(['契約','未填'])
            with self.assertRaisesRegex(ValueError,'Forbidden embedded'): cps.read_xls({'path':'unused'},_data=f.OLE_MAGIC)
            loader.assert_not_called()

class ODSMeaningTests(unittest.TestCase):
    def test_strings_numeric_zero_boolean_exact_precision_date(self):
        result=read(package(table([row(number(0),number('-2.5'),number('9007199254740993'),number('0.123456789012345678901'),cell('true','office:value-type="boolean" office:boolean-value="true"'),cell('2026/10/30','office:value-type="date" office:date-value="2026-10-30"'))])))
        values=[c['raw'] for c in result['sheets'][0]['rows'][0]]
        self.assertEqual(values,[0,-2.5,9007199254740993,'0.123456789012345678901',True,'2026-10-30'])
    def test_formula_cache_states_and_errors_preserved(self):
        values=[cell('2','table:formula="of:=1+1" office:value-type="float" office:value="2"'),cell('display only','table:formula="of:=1+1"'),cell('#DIV/0!','table:formula="of:=1/0" office:value-type="string"'),cell('Err:522','table:formula="of:=A1" calcext:value-type="error"'),cell('bad','office:value-type="float" office:value="NaN"'),cell('text','table:formula="of:=CONCATENATE()" office:value-type="string"')]
        cells=read(package(table([row(*values)])))['sheets'][0]['rows'][0]
        self.assertEqual([c['state'] for c in cells],['cached-formula-value','missing-formula-cache','formula-error','formula-error','error','cached-formula-value'])
        self.assertEqual(cells[0]['raw'],'of:=1+1');self.assertEqual(cells[0]['cached'],2)
        self.assertEqual(cells[5]['cached'],'text');self.assertIsNone(cps.cellvalue(cells[4]))
    def test_bad_types_do_not_become_silent_blank(self):
        cells=read(package(table([row(cell('x','office:value-type="float"'),cell('x','office:value-type="boolean" office:boolean-value="yes"'),cell('x','office:value-type="bogus"'))])))['sheets'][0]['rows'][0]
        self.assertTrue(all(c['state']=='error' and c['native']['value_error'] for c in cells))
    def test_rich_text_space_tab_and_line_break(self):
        value='<table:table-cell office:value-type="string"><text:p>A<text:s text:c="3"/>B<text:tab/>C<text:line-break/>D<text:span>E</text:span></text:p><text:p>F</text:p></table:table-cell>'
        c=read(package(table([row(value)])))['sheets'][0]['rows'][0][0]
        self.assertEqual(c['raw'],'A   B\tC\nDE\nF')
    def test_hidden_style_and_hidden_row_columns(self):
        styles='<style:style style:name="hidden" style:family="table"><style:table-properties table:display="false"/></style:style><style:style style:name="child" style:family="table" style:parent-style-name="hidden"/>'
        columns='<table:table-column table:visibility="collapse" table:number-columns-repeated="2"/>'
        s=read(package(table([columns,row(string('x'),attrs='table:visibility="filter"')],attrs='table:style-name="child"'),styles))['sheets'][0]
        self.assertEqual(s['visibility'],'hidden');self.assertEqual(s['row_visibility'],['filter']);self.assertEqual(s['column_visibility'],['collapse'])
        self.assertEqual(s['column_storage_ranges'][0]['end'],2)
        self.assertEqual(s['column_storage_ranges'][0]['attributes'][f.q('table','visibility')],'collapse')
    def test_merges_and_covered_conflict_are_not_visible_values(self):
        s=read(package(table([row(cell('anchor','office:value-type="string" table:number-columns-spanned="2" table:number-rows-spanned="2"'),cell('residue','office:value-type="string"',True)),row(cell('',covered=True),cell('',covered=True))])))['sheets'][0]
        self.assertEqual(s['merges'],['A1:B2']);self.assertEqual(s['rows'][0][1]['state'],'merged-covered')
        self.assertIsNone(cps.cellvalue(s['rows'][0][1]));self.assertEqual(s['covered_conflicts'][0]['raw'],'residue')
    def test_orphan_overlap_outside_merges_block(self):
        variants=[row(cell('',covered=True)),row(cell('x','table:number-columns-spanned="2"')),row(cell('x','table:number-columns-spanned="2"'),cell('y','table:number-columns-spanned="2"'),string('z'))]
        for value in variants:
            with self.assertRaises(ValueError): read(package(table([value])))
    def test_repeated_rows_cols_coordinates_and_grid_bounds(self):
        value=cell('x','office:value-type="string" table:number-columns-repeated="2"')
        s=read(package(table([row(value,attrs='table:number-rows-repeated="3"')])))['sheets'][0]
        self.assertEqual(s['dimensions'],'A1:B3');self.assertEqual(s['rows'][2][1]['cell'],'B3')
        for rows in ([row(value,attrs='table:number-rows-repeated="20001"')],[row(cell('x','table:number-columns-repeated="1025"'))],[row(cell('x','table:number-columns-repeated="0"'))]):
            with patch.object(f,'ods_cell',side_effect=AssertionError('bound before cell decode')):
                with self.assertRaises(ValueError): read(package(table(rows)))
        with patch.object(f,'MAX_CELLS',5),patch.object(f,'ods_cell',side_effect=AssertionError('bound before cell decode')):
            with self.assertRaisesRegex(ValueError,'rectangular'): read(package(table([row(value,attrs='table:number-rows-repeated="3"')])))
    def test_text_repetition_limit(self):
        value='<table:table-cell office:value-type="string"><text:p><text:s text:c="131073"/></text:p></table:table-cell>'
        with self.assertRaisesRegex(ValueError,'text repetition'): read(package(table([row(value)])))
    def test_sparse_blank_grid_preserves_extents_ranges_and_coordinates(self):
        columns='<table:table-column table:number-columns-repeated="16384" table:visibility="collapse"/>'
        rows=[columns,row(string('header'),'<table:table-cell table:number-columns-repeated="16383" table:style-name="blankstyle"/>'),
              '<table:table-row table:number-rows-repeated="1048575"><table:table-cell table:number-columns-repeated="16384"/></table:table-row>']
        s=read(package(table(rows)))['sheets'][0]
        self.assertEqual(s['dimensions'],'A1:A1');self.assertEqual(s['stored_grid']['dimensions'],'A1:XFD1048576')
        self.assertEqual(len(s['rows']),1);self.assertEqual(s['rows'][0][0]['cell'],'A1')
        self.assertEqual(s['compressed_blank_ranges'][0]['columns'],[2,16384])
        self.assertEqual(s['compressed_blank_ranges'][1]['rows'],[2,1048576])
        self.assertEqual(s['compressed_blank_ranges'][0]['cell_attributes'][f.q('table','style-name')],'blankstyle')
    def test_blank_gap_followed_by_value_formula_cache_or_error_not_elided(self):
        gap='<table:table-row table:number-rows-repeated="20001"><table:table-cell/></table:table-row>'
        values=[string('later value'),cell('','table:formula="of:=1"'),cell('2','table:formula="of:=1+1" office:value-type="float" office:value="2"'),cell('Err:522','calcext:value-type="error"'),'<table:table-cell office:value-type="string"/>']
        for value in values:
            with patch.object(f,'ods_cell',side_effect=AssertionError('must bound before decode')):
                with self.assertRaisesRegex(ValueError,'materialized'): read(package(table([gap,row(value)])))
        for value in values:
            gapcell='<table:table-cell table:number-columns-repeated="1024"/>'
            with self.assertRaisesRegex(ValueError,'materialized'): read(package(table([row(gapcell,value)])))
    def test_sparse_elision_rejects_annotations_merges_or_unknown_attributes(self):
        values=['<table:table-cell table:number-columns-repeated="1025"><office:annotation><text:p>note</text:p></office:annotation></table:table-cell>',
                '<table:table-cell table:number-columns-repeated="1025" table:number-columns-spanned="1"/>',
                '<table:table-cell table:number-columns-repeated="1025" table:content-validation-name="v"/>']
        for value in values:
            with self.assertRaisesRegex(ValueError,'materialized'): read(package(table([row(value)])))
    def test_logical_sparse_grid_limits_still_apply(self):
        for rows in (['<table:table-row table:number-rows-repeated="1048577"><table:table-cell/></table:table-row>'],[row('<table:table-cell table:number-columns-repeated="16385"/>')]):
            with self.assertRaises(ValueError): read(package(table(rows)))
    def test_internal_blank_repeats_keep_source_row_numbers(self):
        rows=[row(string('first')),'<table:table-row table:number-rows-repeated="5"><table:table-cell/></table:table-row>',row(string('last'))]
        s=read(package(table(rows)))['sheets'][0]
        self.assertEqual(len(s['rows']),7);self.assertEqual(s['rows'][6][0]['cell'],'A7');self.assertEqual(s['rows'][6][0]['raw'],'last')
    def test_typed_empty_string_cache_not_missing(self):
        s=read(package(table([row('<table:table-cell table:formula="of:=A1" office:value-type="string"/>')])))['sheets'][0]
        self.assertEqual(s['rows'][0][0]['state'],'cached-formula-value');self.assertEqual(s['rows'][0][0]['cached'],'')
    def test_external_reference_is_recorded_never_resolved(self):
        value='<table:table-cell office:value-type="string"><text:p><text:a xlink:href="https://invalid.invalid/must-not-open">source</text:a></text:p></table:table-cell>'
        result=read(package(table([row(value)])))
        self.assertTrue(result['external_links_present']);self.assertEqual(result['sheets'][0]['rows'][0][0]['raw'],'source')
    def test_source_only_seventeen_column_generation_unverified(self):
        rows=[row(*(string(x) for x in ['項次','品名','規格','單位','數量','單價'])),row(string('1'),string('安裝服務'),string('AC220V'),string('式'),number(2),number(0))]
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'contract.xls';path.write_bytes(package(table(rows)))
            case={'case_id':'synthetic_ods','scope_status':'unverified','sources':[{'path':str(path),'sha256':cps.sha(path),'role':'contract'}]}
            manifest={'schema_version':1,'allowed_source_paths':[str(path)],'contracts':[case]}
            result=cps.generate_contract(case,manifest)
            self.assertEqual(result['status'],'partial');self.assertEqual(len(result['rows'][0]['values']),17)
            self.assertEqual(result['rows'][0]['values'][2:6],['安裝服務','AC220V','式',2])
            self.assertIsNone(result['rows'][0]['values'][16]);self.assertEqual(result['unattended_release'],'blocked')
            self.assertTrue(result['coverage_complete']);self.assertEqual(result['deployment_status'],'NOT_APPROVED')

if __name__=='__main__': unittest.main(verbosity=2)
