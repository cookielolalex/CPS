"""Target-blind synthetic regressions. No original/historical workbook reads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import cps

def fixture(rows):
    return {'path':'synthetic_contract.xlsx','sha256':'a'*64,'sheets':[]}, {
        'name':'Synthetic detail','visibility':'visible','dimensions':'A1:J20','merges':[],
        'covered_conflicts':[],'rows':[[{'cell':f'{cps.colname(i)}{rn}','raw':v,'cached':None,'state':'blank' if v is None else 'literal'} for i,v in enumerate(r,1)] for rn,r in enumerate(rows,1)]}

HEADER=['項次','品名','規格','單位','數量','單價','備註','型號','廠牌']
ADOPT={'authority':'contract_detail','basis':'synthetic signed scope evidence'}
CASE={'case_id':'synthetic','scope_status':'verified'}
def parse(rows,adoption=ADOPT,case=None):
    book,sheet=fixture(rows)
    return cps.parse_sheet(book,sheet,adoption,case or CASE)

class ParserTests(unittest.TestCase):
    def test_seventeen_fields_no_procurement_defaults(self):
        s,rows=parse([HEADER,['1','安裝服務','AC220V','式',2,0,'供料','M-1','BrandX']])
        r=rows[0];self.assertEqual(len(r['values']),17)
        self.assertEqual(r['values'][2],'安裝服務');self.assertEqual(r['values'][16],0)
        self.assertIsNone(r['values'][6]);self.assertIsNone(r['values'][7]);self.assertIsNone(r['values'][15])
        self.assertEqual(r['values'][8:10],['M-1','BrandX']);self.assertEqual(r['commercial_markers'][0]['value'],'供料')
        self.assertEqual(r['field_provenance']['F']['sources'][0]['cell'],'E2')
    def test_unverified_scope_diagnostic_candidate(self):
        s,rows=parse([HEADER,['1','開關','','只',1,3]],adoption=None,case={'case_id':'test','scope_status':'unverified'})
        self.assertEqual(rows[0]['release_state'],'PARTIAL_REVIEW_REQUIRED')
        self.assertTrue(s['review_reasons'])
    def test_explicit_review_only_no_materials(self):
        s,rows=parse([HEADER,['1','開關','','只',1,3]],case={'case_id':'test','scope_status':'partial','generation_mode':'review_only'})
        self.assertEqual(rows,[]);self.assertEqual(len(s['row_dispositions']),2)
    def test_missing_qty_no_zero_or_multiplication(self):
        s,rows=parse([HEADER,['1','開關','','只',None,None]])
        self.assertIsNone(rows[0]['values'][5]);self.assertIsNone(rows[0]['values'][16])
        self.assertEqual(rows[0]['status'],'partial')
    def test_nonprice_markers_not_deleted_or_brand(self):
        s,rows=parse([HEADER,['1','運費','','式',1,'不含估價','客戶自運']])
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['values'][16]);self.assertIsNone(rows[0]['values'][9])
    def test_spec_fragments_preserve_separator(self):
        s,rows=parse([HEADER,['1','箱體','SUS304','只',2,5,'2mm'],[None,None,'IP55',None,None,None,'戶外']])
        self.assertEqual(rows[0]['values'][3],'SUS304\nIP55\n2mm\n戶外')
        self.assertEqual(rows[0]['source_rows'],[2,3])
    def test_description_before_remark_stream(self):
        s,rows=parse([HEADER,['1','組裝安','','式',1,1,'技術備註'],[None,'裝服務',None,None,None,None,None]])
        self.assertEqual(rows[0]['values'][2],'組裝安\n裝服務');self.assertEqual(rows[0]['values'][3],'技術備註')
    def test_description_fragments_never_fuse_numeric_ratings(self):
        s,rows=parse([HEADER,['1','SUS304',None,'只',1,1,None],[None,'2mm',None,None,None,None,None]])
        self.assertEqual(rows[0]['values'][2],'SUS304\n2mm')
    def test_initial_blank_spec_then_spec_continuation(self):
        s,rows=parse([HEADER,['1','開關',None,'只',1,1,None],[None,None,'2P',None,None,None,'220V']])
        self.assertEqual(rows[0]['values'][3],'2P\n220V')
        self.assertEqual(len(rows[0]['field_provenance']['D']['sources']),2)
    def test_panel_ancestry_terminates_at_sibling(self):
        s,rows=parse([HEADER,['1','控制盤 PANEL A','室外','式',1,0],['1.1','開關','','只',3,2],['2','馬達','','只',1,4]])
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['values'][0],'控制盤 PANEL A');self.assertEqual(rows[0]['values'][5],3)
        self.assertIsNone(rows[1]['values'][0]);self.assertEqual(rows[0]['field_provenance']['A']['physical_inside'],'unproven')
    def test_panel_title_continuation(self):
        s,rows=parse([HEADER,['1','控制盤 PANEL A/',None,None,None,None],[None,'B 前後區',None,None,None,None],['1.1','開關',None,'只',2,3]])
        self.assertEqual(rows[0]['values'][0],'控制盤 PANEL A/\nB 前後區')
    def test_panel_title_numeric_fragments_not_fused(self):
        s,rows=parse([HEADER,['1','控制盤 SUS304',None,None,None,None],[None,'2mm',None,None,None,None],['1.1','開關',None,'只',2,3]])
        self.assertEqual(rows[0]['values'][0],'控制盤 SUS304\n2mm')
    def test_continuation_explicit_roles_and_commercial_markers(self):
        s,rows=parse([HEADER,['1','開關',None,'只',1,None],[None,'延續說明',None,None,None,25,'客戶自運','MODEL-X','BRAND-X']])
        r=rows[0];self.assertEqual(r['values'][8:10],['MODEL-X','BRAND-X']);self.assertEqual(r['values'][16],25)
        self.assertTrue(any(x['value']=='客戶自運' for x in r['commercial_markers']))
        self.assertEqual(r['field_provenance']['Q']['sources'][0]['cell'],'F3')
    def test_conflicting_continuation_roles_preserve_existing_and_anomaly(self):
        s,rows=parse([HEADER,['1','開關',None,'只',1,10,None,'M-1','B-1'],[None,None,None,None,None,25,None,'M-2','B-2']])
        r=rows[0];self.assertEqual(r['values'][8:10],['M-1','B-1']);self.assertEqual(r['values'][16],10)
        self.assertEqual({a['field'] for a in r['continuation_anomalies']},{'I','J','Q'});self.assertEqual(r['status'],'partial')
    def test_error_only_continuation_specification_routed(self):
        b,s=fixture([HEADER,['1','開關',None,'只',1,10],[None,None,'#REF!',None,None,None,None,None,None]])
        s['rows'][2][2]['state']='formula-error';record,rows=cps.parse_sheet(b,s,ADOPT,CASE)
        self.assertEqual(record['row_dispositions'][2]['kind'],'continuation')
        self.assertEqual(rows[0]['status'],'partial');self.assertEqual(rows[0]['continuation_anomalies'][0]['source']['cell'],'C3')
    def test_unit_alone_does_not_prove_panel(self):
        s,rows=parse([HEADER,['1','設備工程','','式',None,None],['1.1','開關','','只',1,3]])
        self.assertTrue(all(r['values'][0] is None for r in rows))
    def test_service_without_index_retained(self):
        s,rows=parse([HEADER,[None,'現場安裝服務',None,'式',1,50]])
        self.assertEqual(rows[0]['values'][2],'現場安裝服務')
    def test_two_row_header_uses_positions(self):
        s,rows=parse([['項次','工程項目','規格','單位',None,None],[None,None,None,None,'數量','單價'],['1','開關','2P','只',2,5]])
        self.assertEqual(rows[0]['values'][5],2);self.assertEqual(rows[0]['values'][16],5)
    def test_item_header_and_description_not_confused_after_preamble(self):
        for name in ['名稱 · 規範',' 說                                        明']:
            s,rows=parse([['工程名稱：合成工程'],['項 目',name,'單位','數 量','單 價'],['2.1','NFB 3P 220V','只',2,5]])
            self.assertEqual(rows[0]['values'][2],'NFB 3P 220V')
            self.assertEqual(s['row_dispositions'][0]['kind'],'preamble')
            self.assertEqual(s['row_dispositions'][1]['kind'],'header')
    def test_merged_item_name_pair_two_row_change_header(self):
        b,s=fixture([['工 程 項 目',None,'說 明','單位','變更後',None,None,'備註'],[None,None,None,None,'數量','單價','複價',None],['壹.一.13.a','閥類設備更新','Ø600mm','處',1,None,None,'新增項目']])
        s['rows'][0][1].update(state='merged-covered',anchor='A1');s['merges']=['A1:B2']
        result,rows=cps.parse_sheet(b,s,ADOPT,CASE)
        self.assertEqual(rows[0]['values'][2],'閥類設備更新');self.assertEqual(rows[0]['values'][3],'Ø600mm\n新增項目')
        self.assertEqual(rows[0]['field_provenance']['C']['sources'][0]['cell'],'B3')
    def test_analysis_never_promoted(self):
        b,s=fixture([['工料名稱','單位','數量','單價'],['開關','只',2,3]]);s['name']='單價分析'
        record,rows=cps.parse_sheet(b,s,ADOPT,CASE)
        self.assertEqual(rows,[]);self.assertEqual(len(record['row_dispositions']),2)
    def test_errors_block_key_rows(self):
        b,s=fixture([HEADER,['1','開關','','只','#REF!',3]])
        s['rows'][1][4]['state']='formula-error'
        record,rows=cps.parse_sheet(b,s,ADOPT,CASE)
        self.assertEqual(rows,[]);self.assertEqual(record['row_dispositions'][1]['kind'],'blocked_key_fields')
    def test_merged_covered_error_not_visible_value(self):
        self.assertIsNone(cps.cellvalue({'state':'merged-covered','raw':'duplicate','cached':None}))
    def test_hidden_sheet_gates_completion(self):
        b,s=fixture([HEADER,['1','開關','','只',1,3]]);s['visibility']='hidden'
        result,rows=cps.parse_sheet(b,s,ADOPT,CASE)
        self.assertTrue(any('Hidden' in r for r in result['review_reasons']))
    def test_duplicate_code_not_deduplicated(self):
        s,rows=parse([HEADER,['1','開關','','只',1,2,'1234567'],['2','開關','','只',1,4,'1234567']])
        self.assertEqual(len(rows),2);self.assertEqual([r['values'][16] for r in rows],[2,4])
    def test_heading_cannot_append_to_material(self):
        s,rows=parse([HEADER,['1','開關','','只',1,2],[None,'新控制盤',None,None,None,None]])
        self.assertEqual(rows[0]['values'][2],'開關');self.assertEqual(s['row_dispositions'][-1]['kind'],'ambiguous_heading')
    def test_unsupported_source_has_complete_dispositions(self):
        s,rows=parse([['工程名稱','某工程'],['總價',123]],adoption=None)
        self.assertEqual(rows,[]);self.assertEqual(len(s['row_dispositions']),2)
    def test_pure_parser_also_defends_forbidden_embedded_sheet(self):
        b,s=fixture([HEADER,['1','開關',None,'只',1,3]]);s['name']='已填'
        with self.assertRaisesRegex(ValueError,'Forbidden embedded'): cps.parse_sheet(b,s,ADOPT,CASE)

class IOTests(unittest.TestCase):
    def test_embedded_forbidden_sheet_rejected_before_workbook_loader(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            for name in ['未填','已填','OK','電機圖','板金','原材料清單']:
                path=Path(temp)/'synthetic_contract.xlsx';w=Workbook();w.active.title=name;w.active['A1']='forbidden sentinel';w.save(path);w.close()
                with patch('openpyxl.load_workbook',side_effect=AssertionError('Worksheet loader must not be reached')) as loader:
                    with self.assertRaisesRegex(ValueError,'Forbidden embedded'): cps.read_xlsx({'path':str(path)})
                    loader.assert_not_called()
    def test_manifest_requires_allowlisted_pinned_contracts(self):
        path=Path(__file__).parent/'synthetic_contract.xlsx'
        m={'schema_version':1,'allowed_source_paths':[str(path)],'contracts':[{'case_id':'test','sources':[{'path':str(path),'role':'contract','sha256':'a'*64}]}]}
        self.assertTrue(cps.validate_manifest(m))
        m['allowed_source_paths']=[str(path.parent/'other.xlsx')]
        with self.assertRaises(ValueError): cps.validate_manifest(m)
    def test_forbidden_input_paths(self):
        for name in ['未填.xlsx','已填.xlsx','板金.xlsx','電機圖.xlsx','historical.xlsx','OK.xlsx','supplemental_research/c.xlsx']:
            with self.assertRaises(ValueError,msg=name): cps.reject_source(Path(name))
    def test_real_xlsx_cache_merge_and_error(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path=Path(temp)/'synthetic_contract.xlsx'; w=Workbook();s=w.active;s.title='detail'
            s.append(HEADER);s.append(['1','開關','','只','=1+1',3]);s.append(['2','馬達','','只','=1/0',4]);s.merge_cells('B4:C4');s['B4']='anchor';s['E5']='=2+2';w.save(path);w.close()
            with zipfile.ZipFile(path) as z: members={n:z.read(n) for n in z.namelist()}
            text=members['xl/worksheets/sheet1.xml'].decode()
            text=text.replace('<c r="E2"><f>1+1</f><v></v></c>','<c r="E2"><f>1+1</f><v>2</v></c>')
            text=text.replace('<c r="E3"><f>1/0</f><v></v></c>','<c r="E3" t="e"><f>1/0</f><v>#DIV/0!</v></c>')
            text=text.replace('</sheetData>','<row r="6"><c r="B6" t="inlineStr"><is><t>end</t></is></c></row></sheetData>')
            text=text.replace('<c r="B4" t="inlineStr"><is><t>anchor</t></is></c>','<c r="B4" t="inlineStr"><is><t>anchor</t></is></c><c r="C4" t="inlineStr"><is><t>covered conflict</t></is></c>')
            members['xl/worksheets/sheet1.xml']=text.encode()
            with zipfile.ZipFile(path,'w') as z:
                for n,data in members.items(): z.writestr(n,data)
            source={'path':str(path),'sha256':cps.sha(path),'role':'contract'}
            book=cps.read_source(source);sheet=book['sheets'][0]
            self.assertEqual(sheet['rows'][1][4]['state'],'cached-formula-value')
            self.assertEqual(sheet['rows'][1][4]['cached'],2)
            self.assertEqual(sheet['rows'][2][4]['state'],'formula-error')
            self.assertEqual(sheet['rows'][4][4]['state'],'missing-formula-cache')
            self.assertEqual(sheet['rows'][3][2]['state'],'merged-covered')
            self.assertEqual(sheet['covered_conflicts'][0]['native']['inline_text'],'covered conflict')
            source['sha256']='a'*64
            with self.assertRaises(ValueError): cps.read_source(source)
    def test_batch_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            p=Path(temp);(p/'existing').write_text('x')
            source=str(p/'synthetic_contract.xlsx')
            m={'schema_version':1,'allowed_source_paths':[source],'contracts':[{'case_id':'test','sources':[{'path':source,'role':'contract','sha256':'a'*64}]}]}
            with self.assertRaises(ValueError): cps.batch_generate(m,p)
    def test_missing_and_corrupt_sources_block_without_claimed_coverage(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path=Path(temp)/'synthetic_contract.xlsx'
            case={'case_id':'test','scope_status':'partial','sources':[{'path':str(path),'role':'contract','sha256':'a'*64}]}
            manifest={'schema_version':1,'allowed_source_paths':[str(path)],'contracts':[case]}
            result=cps.generate_contract(case,manifest)
            self.assertEqual(result['status'],'blocked');self.assertFalse(result['coverage_complete'])
            path.write_bytes(b'not an Excel file');case['sources'][0]['sha256']=cps.sha(path)
            result=cps.generate_contract(case,manifest)
            self.assertEqual(result['status'],'blocked');self.assertFalse(result['coverage_complete'])
    def test_numeric_boundaries(self):
        for value,expected in [(0,0),(-2,-2),(0.125,0.125),('1,234.50','1,234.50'),(None,None),('',None),('#REF!',None),(True,None),(float('nan'),None),('供料',None)]:
            self.assertEqual(cps.numeric(value),expected)
    def test_exact_text_numerals_and_malformed_grouping(self):
        for value in ['9007199254740993','0.12345678901234567890123456789','1,234,567.890000']:
            self.assertEqual(cps.numeric(value),value)
        for value in ['1,2','12,34','1,234,56','1,,234','1,234.5,6','1e3']:
            self.assertIsNone(cps.numeric(value))
        s,rows=parse([HEADER,['1','材料',None,'只','1,2','9007199254740993']])
        self.assertEqual(rows[0]['values'][5],'1,2');self.assertEqual(rows[0]['status'],'partial')
        self.assertEqual(rows[0]['values'][16],'9007199254740993')
    def test_financial_quantity_annotation_preserved_and_flagged(self):
        s,rows=parse([HEADER,['1','材料',None,'只','供料',None]])
        self.assertEqual(rows[0]['values'][5],'供料');self.assertEqual(rows[0]['status'],'partial')
        self.assertTrue(any('nonnumeric' in reason for reason in rows[0]['review_reasons']))

if __name__=='__main__': unittest.main(verbosity=2)
