"""Write the 046b JSON schemas deterministically (structural contracts only)."""
import json
from pathlib import Path
OUT = Path(__file__).resolve().parents[1] / 'package' / 'resources'
ID = {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$'}
CELL = {'type': 'string', 'pattern': '^cell:S[1-9][0-9]{0,3}![A-Z]{1,3}[1-9][0-9]{0,6}$'}
CTX = {'type': 'string', 'pattern': '^context:[a-z0-9_]{1,64}$'}
TXT = {'type': 'string', 'minLength': 1, 'maxLength': 30000}
NTXT = {'type': ['string', 'null'], 'maxLength': 30000}
NUM = {'type': ['number', 'null']}
def arr(x, mn=0, unique=True):
    d = {'type': 'array', 'items': x}
    if mn: d['minItems'] = mn
    if unique: d['uniqueItems'] = True
    return d
def obj(props, req=None):
    return {'type': 'object', 'properties': props, 'required': list(req or props), 'additionalProperties': False}

nonnull_proof = obj({'refs': arr({'anyOf': [CELL, CTX]}, 1), 'transformation': TXT, 'role_basis': TXT})
null_proof = obj({'reason': TXT})
proof = {'oneOf': [{'$ref': '#/$defs/nonnull_proof'}, {'$ref': '#/$defs/null_proof'}]}
raw_sel = obj({'refs': arr(CELL), 'reason_if_empty': {'type': ['string', 'null'], 'minLength': 1}})
single_raw = obj({'refs': {**arr(CELL), 'maxItems': 1}, 'reason_if_empty': {'type': ['string', 'null'], 'minLength': 1}})
value_items = [NTXT] * 5 + [NUM, {'type': 'null'}, {'type': 'null'}] + [NTXT] * 7 + [NUM, NUM]
item = obj({
    'id': ID, 'role': {'enum': ['demand', 'analysis_component']}, 'group_id': {'anyOf': [ID, {'type': 'null'}]},
    'status': {'enum': ['research_draft', 'held']},
    'values': {'type': 'array', 'prefixItems': value_items, 'items': False, 'minItems': 17, 'maxItems': 17},
    'proofs': obj({c: proof for c in 'ABCDEFGHIJKLMNOPQ'}),
    'raw_refs': obj({'description': raw_sel, 'unit': single_raw, 'quantity': single_raw, 'unit_price': single_raw,
                     'amount': single_raw, 'remarks': raw_sel}),
    'anchor_refs': arr(CELL, 1), 'review_reasons': {'type': 'array', 'items': TXT, 'maxItems': 500}})
group = obj({'id': ID, 'name': NTXT, 'specification': NTXT,
             'relationship': {'enum': ['contractual_group', 'physical_enclosure', 'contractual_and_physical', 'unresolved']},
             'anchor_refs': arr(CELL, 1), 'name_refs': arr(CELL), 'specification_refs': arr(CELL),
             'quantity_basis': TXT, 'limitations': {'type': 'array', 'items': TXT}})
link = obj({'component_id': ID, 'parent_id': {'anyOf': [ID, {'type': 'null'}]}, 'status': {'enum': ['supported', 'held']},
            'basis_quantity': {'type': ['number', 'null'], 'exclusiveMinimum': 0},
            'basis_raw_ref': {'anyOf': [CELL, {'type': 'null'}]}, 'basis_unit_ref': {'anyOf': [CELL, {'type': 'null'}]},
            'refs': arr(CELL), 'reason': TXT})
role = obj({'role': {'enum': ['demand_content', 'analysis_content', 'item_identifier', 'header', 'section',
                              'financial_summary', 'commercial_note', 'document_reference', 'footer', 'unresolved']},
            'refs': arr(CELL, 1), 'reason': TXT})
response = obj({'schema': {'const': 'cps.semantic-source-refs.v2'}, 'case_id': ID, 'family_id': ID,
                'inventory_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                'status': {'enum': ['research_draft', 'partial', 'held']},
                'groups': {'type': 'array', 'items': {'$ref': '#/$defs/group'}},
                'items': {'type': 'array', 'items': {'$ref': '#/$defs/item'}, 'minItems': 1, 'maxItems': 2000},
                'component_links': {'type': 'array', 'items': {'$ref': '#/$defs/component_link'}},
                'source_roles': {'type': 'array', 'items': {'$ref': '#/$defs/source_role'}},
                'limitations': {'type': 'array', 'items': TXT, 'maxItems': 400}})
response.update({'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:cps:semantic-source-refs:v2',
                 '$defs': {'nonnull_proof': nonnull_proof, 'null_proof': null_proof, 'item': item, 'group': group,
                           'component_link': link, 'source_role': role},
                 'description': 'Candidate 046b structural contract. values[0..16] map A..Q. Schema conformance is necessary, not sufficient: tools/cps046b_route.py check enforces reference identity, value/proof consistency, writer004 compatibility, group/component/census rules. Neither is semantic acceptance.'})

pin = obj({'file': TXT, 'bytes': {'type': 'integer', 'minimum': 1}, 'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}})
view = obj({'id': {'type': 'integer', 'minimum': 1}, 'sheet': TXT, 'range': {'type': 'string', 'pattern': '^[A-Z]{1,3}[1-9][0-9]*(:[A-Z]{1,3}[1-9][0-9]*)?$'}})
cell = obj({'ref': CELL, 'sheet_index': {'type': 'integer', 'minimum': 1}, 'sheet': TXT,
            'address': {'type': 'string', 'pattern': '^[A-Z]{1,3}[1-9][0-9]{0,6}$'},
            'row': {'type': 'integer', 'minimum': 1}, 'col': {'type': 'integer', 'minimum': 1},
            'saved_type': {'enum': ['empty', 'blank', 'text', 'number', 'date', 'boolean', 'error']},
            'state': {'enum': ['literal', 'cached_formula', 'true_blank', 'explicit_empty', 'covered', 'error', 'missing_cache', 'unresolved']},
            'saved_value': {'type': ['string', 'number', 'boolean', 'null']}, 'native_literal': NTXT,
            'formula_record_present': {'type': 'boolean'}, 'formula': NTXT,
            'merge_anchor_ref': {'anyOf': [CELL, {'type': 'null'}]}, 'conflicts': {'type': 'array', 'items': TXT},
            'canonical_raw': NTXT, 'usable_for_raw': {'type': 'boolean'}, 'raw_limit_reason': NTXT,
            'views': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1}}})
inventory = obj({
    'schema': {'const': 'cps.source-inventory.cells.v2'}, 'case_id': ID, 'family_id': ID,
    'representation_profile': {'const': 'cached-cell-raw-scalar-text.v2'},
    'source': obj({'source_id': {'const': 'S'}, 'format': {'enum': ['cached_xls', 'cached_xlsx']},
                   'bytes': {'type': 'integer', 'minimum': 1}, 'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                   'adoption_status': {'enum': ['verified', 'partial', 'unverified']}, 'adoption_basis': TXT,
                   'reader': obj({'name': TXT, 'version': TXT, 'biff_format': NTXT, 'formula_expressions_available': {'type': 'boolean'}}),
                   'carrier_source': obj({'kind': {'enum': ['cached_xls', 'cached_xlsx']}, 'path': TXT,
                                          'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}, 'views': {'type': 'array', 'items': view, 'minItems': 1}})}),
    'sheets': {'type': 'array', 'items': obj({'index': {'type': 'integer', 'minimum': 1}, 'name': TXT,
                                              'visibility': {'enum': ['visible', 'hidden', 'very_hidden']},
                                              'rows': {'type': 'integer', 'minimum': 0}, 'columns': {'type': 'integer', 'minimum': 0},
                                              'merges': {'type': 'array', 'items': {'type': 'string'}},
                                              'formula_records': {'type': 'integer', 'minimum': 0}, 'in_scope': {'type': 'boolean'}}), 'minItems': 1},
    'views': {'type': 'array', 'items': obj({**view['properties'], 'image': pin}), 'minItems': 1},
    'external_links': {'type': 'array', 'items': {'type': 'object'}},
    'cells': {'type': 'array', 'items': cell, 'minItems': 1},
    'context_facts': {'type': 'array', 'items': obj({'ref': CTX, 'namespace': TXT, 'value': {'type': ['string', 'number', 'null']}, 'basis': TXT,
                                                     'authority_pins': {'type': 'array', 'items': obj({'label': TXT, 'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}), 'minItems': 1}})},
    'limitations': {'type': 'array', 'items': TXT}})
inventory.update({'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:cps:source-inventory:cells:v2',
                  'description': 'Candidate 046b complete positional inventory of one pinned cached workbook. Every physical position of every in-scope sheet appears once; carrier_source is copied verbatim into the writer carrier; the inventory file sha256 binds a response. Structural contract only.'})
for name, d in (('SEMANTIC_RESPONSE.schema.json', response), ('SOURCE_INVENTORY.schema.json', inventory)):
    (OUT / name).write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print('schemas written')
