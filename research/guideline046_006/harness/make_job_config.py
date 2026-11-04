"""Write the inventory-builder config for one 046f job packet, with the job-input and company-resource context facts.

Source-preparation role only (owner decisions O13-O17; FIELD_ROLES R47b, R48, R58). Reads the private job JSON,
the owner-reviewed glossary and brand table files it names, and the source file's bytes (only to pin size and
sha256). It never reads historical worksheets, targets, evaluator files or anything else, and it prints no
private values. The output config is consumed unchanged by the existing builders, which copy `context_facts`
verbatim into SOURCE_INVENTORY.json:
  .xlsx: research/guideline046_003/source_prep/build_inventory_xlsx_v2.py --bundle DIR --config CONFIG --out NEWDIR
  .xls:  research/guideline046_003/source_prep/build_inventory_v2.py      --bundle DIR --config CONFIG --out NEWDIR

Usage: python3 -I -B make_job_config.py --job /abs/private/JOB.json --out /abs/new/BUILDER_CONFIG.json

Job JSON (schema cps.job-config.v2; one source per config: a job with both a 材料清單 and a contract needs two):
  required: schema, case_id, customer_name, project_name, company_name, glossary_path, brand_table_path,
            source_path, source_kind ("材料清單" or "contract"), carrier_path (the original Windows path of the
            source, provenance only, e.g. "X:\\Jobs\\...\\file.xlsx")
  optional: family_id (default case_id), adoption_status ("verified"|"partial"|"unverified", default
            "unverified"), adoption_basis, views ("auto" or the builder's view list, default "auto"),
            provenance {job_inputs, glossary_review, brand_table_review} (strings for the facts' basis)
Context facts written (route v4.1 names): context:case_identity, context:customer_name, context:project_name,
context:company_name, context:glossary, context:brand_table. The glossary and brand table values are their
files' JSON re-serialised as compact JSON text (key order kept); each basis names the sha256 of the file bytes
and of the embedded text, and both are pinned in authority_pins.
"""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROUTE = HERE.parent / 'package' / 'tools' / 'cps046b_route.py'
JOB_SCHEMA = 'cps.job-config.v2'
CONFIG_SCHEMA = 'cps.source-prep-builder-config.v2'
KINDS = {'材料清單': 'company material list (材料清單), the primary job source when present (O17, FIELD_ROLES R47b)',
         'contract': 'contract; the job has no material list, so rows come from the contract (FIELD_ROLES R47b)'}
REQUIRED = ('schema', 'case_id', 'customer_name', 'project_name', 'company_name', 'glossary_path', 'brand_table_path',
            'source_path', 'source_kind', 'carrier_path')
OPTIONAL = ('family_id', 'adoption_status', 'adoption_basis', 'views', 'provenance')
BUILDERS = {'.xlsx': ('cached_xlsx', 'research/guideline046_003/source_prep/build_inventory_xlsx_v2.py'),
            '.xls': ('cached_xls', 'research/guideline046_003/source_prep/build_inventory_v2.py')}
RESOURCES = {
    'glossary': ('cps.company-glossary.v1', {'generic_prefix_words': list, 'enclosure_word': str, 'abbreviations': list},
                 {'category_words': list}, ('device', 'abbreviation')),
    'brand_table': ('cps.company-brand-table.v1', {'entries': list}, {}, ('device', 'rating_band', 'brand', 'model')),
}


class Refused(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_route():
    spec = importlib.util.spec_from_file_location('cps046f_route_for_job_config', ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def strict_json(route, raw, what):
    try:
        return route.strict_load(raw)
    except route.Rejected as e:
        raise Refused('INVALID_JSON', {'file': what, 'error': str(e)})


def writer_safe(route, value, key):
    """A job input is copied verbatim into M/N/L or J; refuse values the route would reject or hold."""
    rep = route.Report()
    if not isinstance(value, str) or not route.writer_text(value, key, rep) or rep.violations:
        raise Refused('JOB_INPUT_NOT_WRITER_SAFE', {'key': key, 'codes': [v['code'] for v in rep.violations] or ['STRING_REQUIRED']})
    if value != value.strip(route.JS_WS):
        raise Refused('JOB_INPUT_EDGE_WHITESPACE', {'key': key})


def resource(route, name, path):
    schema, required, optional, entry_keys = RESOURCES[name]
    p = Path(path)
    if not p.is_absolute() or not p.is_file():
        raise Refused('RESOURCE_FILE_REQUIRED', {'resource': name})
    raw = p.read_bytes()
    obj = strict_json(route, raw, name)
    if not isinstance(obj, dict) or obj.get('schema') != schema:
        raise Refused('RESOURCE_SCHEMA', {'resource': name, 'expected': schema})
    for k, t in list(required.items()) + [(k, t) for k, t in optional.items() if k in obj]:
        if not isinstance(obj.get(k), t):
            raise Refused('RESOURCE_SHAPE', {'resource': name, 'key': k})
    rows = obj.get('abbreviations' if name == 'glossary' else 'entries')
    if not rows or not all(isinstance(r, dict) and all(isinstance(r.get(k), str) and r[k].strip() for k in entry_keys) for r in rows):
        raise Refused('RESOURCE_SHAPE', {'resource': name, 'entries_need': list(entry_keys)})
    text = json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return text, sha(raw), sha(text.encode('utf-8'))


def build_config(job_path):
    route = load_route()
    job_raw = job_path.read_bytes()
    job = strict_json(route, job_raw, 'job')
    if not isinstance(job, dict):
        raise Refused('JOB_OBJECT_REQUIRED')
    missing = [k for k in REQUIRED if k not in job]
    extra = [k for k in job if k not in REQUIRED + OPTIONAL]
    if missing or extra:
        raise Refused('JOB_KEYS', {'missing': missing, 'unexpected': extra})
    if job['schema'] != JOB_SCHEMA:
        raise Refused('JOB_SCHEMA', {'expected': JOB_SCHEMA})
    family = job.get('family_id', job['case_id'])
    for k, v in (('case_id', job['case_id']), ('family_id', family)):
        if not isinstance(v, str) or not route.ID_RE.fullmatch(v):
            raise Refused('ID_REQUIRED', {'key': k, 'pattern': route.ID_RE.pattern})
    for k in ('case_id', 'customer_name', 'project_name', 'company_name'):
        writer_safe(route, job[k], k)
    if job['source_kind'] not in KINDS:
        raise Refused('SOURCE_KIND', {'allowed': list(KINDS)})
    adoption = job.get('adoption_status', 'unverified')
    if adoption not in ('verified', 'partial', 'unverified'):
        raise Refused('ADOPTION_STATUS', {'allowed': ['verified', 'partial', 'unverified']})
    views = job.get('views', 'auto')
    if views != 'auto' and not isinstance(views, list):
        raise Refused('VIEWS', 'views is "auto" or the builder view list')
    prov = job.get('provenance', {})
    if not isinstance(prov, dict) or any(k not in ('job_inputs', 'glossary_review', 'brand_table_review') or not isinstance(v, str) or not v.strip()
                                         for k, v in prov.items()):
        raise Refused('PROVENANCE', 'provenance holds nonblank strings job_inputs, glossary_review, brand_table_review')
    src = Path(job['source_path'])
    ext = src.suffix.lower()
    if not src.is_absolute() or not src.is_file() or ext not in BUILDERS:
        raise Refused('SOURCE_FILE_REQUIRED', 'an absolute path to an existing .xlsx or .xls file')
    kind, builder = BUILDERS[ext]
    data = src.read_bytes()
    try:                            # the carrier path must already satisfy the writer's source rules (route _source_shape)
        route._source_shape({'kind': kind, 'path': job['carrier_path'], 'sha256': sha(data), 'views': [{'id': 1, 'sheet': 'x', 'range': 'A1'}]},
                            'carrier_path')
    except route.WriterReject as e:
        raise Refused('CARRIER_PATH_' + e.code, 'carrier_path is the original canonical Windows path (provenance only), with the source extension')
    except Exception:               # noqa: BLE001 - a non-string path
        raise Refused('CARRIER_PATH_REQUIRED')
    glossary, g_file, g_text = resource(route, 'glossary', job['glossary_path'])
    brands, b_file, b_text = resource(route, 'brand_table', job['brand_table_path'])
    job_sha = sha(job_raw)
    who = prov.get('job_inputs', 'no provenance statement in the job config')

    def fact(name, namespace, value, basis, pins):
        return {'ref': 'context:' + name, 'namespace': namespace, 'value': value, 'basis': basis,
                'authority_pins': [{'label': label, 'sha256': h} for label, h in pins]}
    job_pin = [('private per-job config (cps.job-config.v2)', job_sha)]
    facts = [
        fact('case_identity', 'cps.internal_case_id', job['case_id'],
             f'Job input supplied with the job (O13, FIELD_ROLES R48): internal case id, copied into L. Supplied by: {who}.', job_pin),
        fact('customer_name', 'cps.job_input.customer_full_name', job['customer_name'],
             f'Job input supplied with the job (O13, FIELD_ROLES R48): customer full name, copied into M. Supplied by: {who}.', job_pin),
        fact('project_name', 'cps.job_input.project_short_name', job['project_name'],
             f'Job input supplied with the job (O13, FIELD_ROLES R48): project short name, copied into N. Supplied by: {who}.', job_pin),
        fact('company_name', 'cps.company_resource.company_name', job['company_name'],
             f'Company name supplied with the job (O16, FIELD_ROLES R56, R58): J of the enclosure row when the source states no brand. Supplied by: {who}.',
             job_pin),
        fact('glossary', 'cps.company_resource.glossary', glossary,
             'Owner-reviewed company abbreviation glossary (O15, FIELD_ROLES R52, R58), embedded as compact JSON text. '
             f'File sha256 {g_file}; embedded text sha256 {g_text}. Review: {prov.get("glossary_review", "no review statement in the job config")}.',
             [('owner-reviewed glossary file', g_file), ('embedded compact JSON text', g_text)]),
        fact('brand_table', 'cps.company_resource.brand_table', brands,
             'Owner-reviewed company brand/model table (O14, O18, FIELD_ROLES R55, R58), the fallback when no source states a brand or model '
             f'(R47b), embedded as compact JSON text. File sha256 {b_file}; embedded text sha256 {b_text}. '
             f'Review: {prov.get("brand_table_review", "no review statement in the job config")}.',
             [('owner-reviewed brand table file', b_file), ('embedded compact JSON text', b_text)]),
    ]
    for f in facts:                 # the route's own inventory rule for context refs
        assert route.CONTEXT_REF_RE.fullmatch(f['ref'])
    basis = f"Source document kind: {job['source_kind']} - {KINDS[job['source_kind']]}. "
    basis += job.get('adoption_basis') or ('No adoption evidence was supplied with the job config; adoption is ' + adoption + '.')
    cfg = {'schema': CONFIG_SCHEMA, 'case_id': job['case_id'], 'family_id': family,
           'source_document_kind': job['source_kind'], 'builder': builder,
           'original': {'path': str(src), 'bytes': len(data), 'sha256': sha(data)},
           'carrier_path': job['carrier_path'], 'views': views,
           'adoption_status': adoption, 'adoption_basis': basis,
           'job_config_sha256': job_sha,
           'resource_files_sha256': {'glossary': g_file, 'brand_table': b_file},
           'context_facts': facts}
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description='Write the 046f inventory-builder config with job-input and resource context facts.')
    ap.add_argument('--job', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        if not a.job.is_absolute() or not a.out.is_absolute():
            raise Refused('ABSOLUTE_PATH_REQUIRED')
        if a.out.exists():
            raise Refused('OUTPUT_EXISTS')
        cfg = build_config(a.job)
    except Refused as e:
        sys.stderr.write(json.dumps({'status': 'REFUSED', 'code': e.code, 'detail': e.detail}, ensure_ascii=False) + '\n')
        return 1
    raw = (json.dumps(cfg, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
    with open(a.out, 'xb') as f:
        f.write(raw)
    print(json.dumps({'status': 'WRITTEN', 'config': str(a.out), 'config_sha256': sha(raw), 'builder': cfg['builder'],
                      'source_document_kind': cfg['source_document_kind'], 'source_sha256': cfg['original']['sha256'],
                      'job_config_sha256': cfg['job_config_sha256'], 'resource_files_sha256': cfg['resource_files_sha256'],
                      'context_facts': [f['ref'] for f in cfg['context_facts']], 'values_printed': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
