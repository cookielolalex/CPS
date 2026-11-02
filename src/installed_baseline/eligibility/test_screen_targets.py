"""Synthetic engine controls; never read an original target."""
import json, tempfile, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import screen_targets as S

def cell(v,row,col,formula=False):
    return SimpleNamespace(value=v,row=row,coordinate=S.openpyxl.utils.get_column_letter(col)+str(row),data_type='f' if formula else 's')

class Sheet:
    def __init__(self,name,rows,formula_cells=(),forbidden=False):self.title=name;self.rows=rows;self.formulas=formula_cells;self.forbidden=forbidden
    def reset_dimensions(self):
        assert not self.forbidden,'Forbidden sheet reset/accessed'
    def iter_rows(self,min_row=1,max_row=None,max_col=64):
        assert not self.forbidden,'Forbidden sheet cells read'
        for ri,raw in enumerate(self.rows,1):
            if ri<min_row or (max_row is not None and ri>max_row):continue
            yield tuple(cell(raw[ci-1] if ci<=len(raw) else None,ri,ci,(ri,ci) in self.formulas) for ci in range(1,max_col+1))

class Book:
    def __init__(self,sheets):self.worksheets=sheets
    def __getitem__(self,name):return next(x for x in self.worksheets if x.title==name)
    def close(self):pass

out=Path(__file__).parent
checks=[]
def check(name,fn):
    fn();checks.append({'name':name,'status':'PASS'})

def engine(rows,formula_rows=None,formula_cells=(),hashes=None,interrupt_after_positive=False):
    cache=Book([Sheet('未填',rows),Sheet('電機圖',[],forbidden=True),Sheet('工作表1',[[None]])])
    fbook=Book([Sheet('未填',formula_rows or rows,formula_cells),Sheet('電機圖',[],forbidden=True),Sheet('工作表1',[[None]])])
    if interrupt_after_positive:
        original_iter=cache.worksheets[0].iter_rows
        def interrupted(*args,**kwargs):
            for row in original_iter(*args,**kwargs):
                yield row
                if kwargs.get('min_row',1)>1:raise RuntimeError('Synthetic interrupted after positive')
        cache.worksheets[0].iter_rows=interrupted
    with tempfile.TemporaryDirectory(dir=out) as td:
        p=Path(td)/'1110101(未填).xlsx';p.write_bytes(b'synthetic-only-no-worksheet-content')
        with patch.object(S.openpyxl,'load_workbook',side_effect=[cache,fbook]):
            if hashes:
                with patch.object(S,'sha',side_effect=hashes):return S.scan(p,time.monotonic()+30)
            return S.scan(p,time.monotonic()+30)

headers=['說明',None,'材料名稱','規格','單位','數量','盤體名稱','盤體規格']
def continuation():
    result=engine([headers,[None,None,'CASE',None,'只',1],[None,None,None,'700W*1100+600H*450D',None,None]])
    assert result['status']=='EXCLUDE_PANEL_DIMENSION_PLUS'
    assert result['qualifying_evidence'][0]['cell']=='D3'
    assert result['qualifying_evidence'][0]['enclosure_continuation'] is True
    assert result['sheets'][1]['status']=='SKIPPED_FORBIDDEN_BEFORE_CELL_ACCESS'
    assert result['sheets'][2]['status']=='EMPTY_COMPLETE_VALUE_AND_FORMULA_STREAMS'
check('Shifted mapped headers + enclosure continuation + forbidden sheet guard',continuation)

def missingcache():
    result=engine([headers,[None,None,'CASE',None,'只',1]],
                  [headers,[None,None,'CASE','=A1','只',1]],[(2,4)])
    assert result['status']=='REVIEW_REQUIRED'
    assert any('Missing relevant formula cache' in x for x in result['reasons'])
check('Missing saved dimension formula cache requires review',missingcache)

def cachedformula():
    result=engine([headers,[None,None,'CASE','700W*1100+600H*450D','只',1]],
                  [headers,[None,None,'CASE','=A1','只',1]],[(2,4)])
    assert result['status']=='EXCLUDE_PANEL_DIMENSION_PLUS'
    assert result['qualifying_evidence'][0]['raw_value']=='700W*1100+600H*450D'
check('Saved formula result screened without evaluating formula',cachedformula)

def unknown():
    assert engine([['不明欄位','說明']])['status']=='REVIEW_REQUIRED'
check('Unknown supply schema never clears',unknown)

def combined_header_not_data():
    result=engine([['盤體名稱','盤體規格','材料名稱','規格+材料名稱','單位','數量'],
                   ['P1','700W*1100H*450D','電控箱','700W*1100H*450D','只',1]])
    assert result['status']=='NO_PANEL_DIMENSION_PLUS_DETECTED'
    assert result['nonqualifying_plus_count']==0 and not result['ambiguous_evidence']
check('Combined specification header plus is never target dimension data',combined_header_not_data)

def late_formula():
    rows=[[None] for _ in range(35)];frows=[[None] for _ in range(34)]+[['=A1']]
    result=engine(rows,frows,[(35,1)])
    assert result['status']=='REVIEW_REQUIRED'
    assert result['sheets'][0]['status']!='EMPTY_COMPLETE_VALUE_AND_FORMULA_STREAMS'
check('Blank first30 rows do not hide later formula in unknown sheet',late_formula)

def changedhash():
    result=engine([headers,[None,None,'CASE','700W*1100+600H*450D','只',1]],hashes=['before','after'])
    assert result['status']=='REVIEW_REQUIRED' and result['hash_unchanged'] is False
check('Changing source bytes invalidate hash-bound classification',changedhash)

def changed_after_exception():
    result=engine([headers,[None,None,'CASE','700W*1100+600H*450D','只',1]],hashes=['before','after'],interrupt_after_positive=True)
    assert result['qualifying_evidence'] and result['status']=='REVIEW_REQUIRED'
    assert result['hash_unchanged'] is False and result['coverage_complete'] is False
check('Source change plus post-positive exception requires review',changed_after_exception)

def stable_after_exception():
    result=engine([headers,[None,None,'CASE','700W*1100+600H*450D','只',1]],hashes=['same','same'],interrupt_after_positive=True)
    assert result['status']=='EXCLUDE_PANEL_DIMENSION_PLUS'
    assert result['hash_unchanged'] is True and result['coverage_complete'] is False
check('Stable source plus positive exception preserves exclusion with incomplete coverage',stable_after_exception)

def hash_error_after_exception():
    result=engine([headers,[None,None,'CASE','700W*1100+600H*450D','只',1]],hashes=['before',OSError('Synthetic hash read failure')],interrupt_after_positive=True)
    assert result['status']=='REVIEW_REQUIRED' and result['hash_unchanged'] is None
    assert result['coverage_complete'] is False
check('Post-positive exception with failed posthash requires review',hash_error_after_exception)

def filename():
    with patch.object(S,'sha',side_effect=AssertionError('Excluded file contents touched')):
        result=S.scan(Path('1110101(未填)(OK).xlsx'),time.monotonic()+30)
    assert result['status']=='SKIPPED_KNOWN_LATER_STAGE_OR_TEMP'
check('Known later-stage filename skipped before any hash or cell read',filename)

result={'status':'PASS','engine_controls':checks,'classification_and_schema_controls':S.controls()}
(out/'ENGINE_CONTROLS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','engine_controls':len(checks),'classification_controls':len(S.controls()['classification_controls']),'additional_boundary_schema_controls':S.controls()['sheet_and_filename_boundary_controls']+S.controls()['shifted_and_unknown_schema_controls']}))
