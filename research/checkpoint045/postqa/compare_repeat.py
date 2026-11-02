"""Compare whole saved data through complete independent XML fidelity checks and identical matrices."""
from pathlib import Path
import argparse,json,hashlib
p=argparse.ArgumentParser();p.add_argument('--original',required=True);p.add_argument('--repeat',required=True);p.add_argument('--qa-original',required=True);p.add_argument('--qa-repeat',required=True);p.add_argument('--report',required=True);a=p.parse_args()
original=Path(a.original);repeat=Path(a.repeat)
ma=json.loads((original/'EXPECTED_SAVED_VALUES.json').read_bytes());mb=json.loads((repeat/'EXPECTED_SAVED_VALUES.json').read_bytes())
qa=json.loads(Path(a.qa_original).read_bytes());qb=json.loads(Path(a.qa_repeat).read_bytes())
for r in [qa,qb]:
    if r['status']!='SAVED_ALL_CELL_VALUE_TYPE_PASS' or r['errors']:raise ValueError('COMPLETE_SAVED_FIDELITY_REQUIRED')
same=ma==mb
source_same=(original/'source-carrier.json').read_bytes()==(repeat/'source-carrier.json').read_bytes()
report={'status':'SAVED_DATA_ASSEMBLY_REPEATABILITY_PASS' if same and source_same else 'SAVED_DATA_ASSEMBLY_REPEATABILITY_FAILED','entire_main_review_matrix_equal':same,'exact_source_carrier_bytes_equal':source_same,'original_all_cells_values_types_formulas_pass':True,'repeat_all_cells_values_types_formulas_pass':True,'original_xlsx_sha256':qa['xlsx_sha256'],'repeat_xlsx_sha256':qb['xlsx_sha256'],'zip_byte_identity_required':False,'reader_repeatability_test':False,'semantic_source_accuracy_test':False,'deployment_credit':False,'visual_QA':'Separate render/inspection required; review views are explicitly sampled'}
with Path(a.report).open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
print(json.dumps(report))
if not same or not source_same:raise SystemExit(1)
