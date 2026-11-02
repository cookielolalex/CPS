"""Narrow, non-mutating subprofile check before the unchanged compact expander."""
PROFILE_ID = 'cps.compact-cached-xlsx.inline-null-reasons.v1'

def require_inline_null_reasons(compact):
    if type(compact) is not dict:
        raise ValueError('INLINE_PROFILE_COMPACT_OBJECT_REQUIRED')
    reasons = compact.get('reasons')
    if type(reasons) is not dict or reasons:
        raise ValueError('INLINE_PROFILE_EMPTY_REASONS_REQUIRED')
    fieldsets = compact.get('fieldsets')
    if type(fieldsets) is not dict:
        raise ValueError('INLINE_PROFILE_FIELDSETS_OBJECT_REQUIRED')
    counts = {'fieldset_null_declarations': 0, 'local_null_declarations': 0}

    def inspect_fields(fields, counter):
        if type(fields) is not dict:
            raise ValueError('INLINE_PROFILE_FIELD_MAP_REQUIRED')
        for pair in fields.values():
            if type(pair) is not list or len(pair) != 2:
                raise ValueError('INLINE_PROFILE_FIELD_PAIR_REQUIRED')
            value, proof = pair
            if value is None:
                if type(proof) is not str or not proof.strip():
                    raise ValueError('INLINE_NULL_REASON_REQUIRED')
                counts[counter] += 1

    for fields in fieldsets.values():
        inspect_fields(fields, 'fieldset_null_declarations')
    for kind, length in [('items', 9), ('components', 10)]:
        rows = compact.get(kind)
        if type(rows) is not list:
            raise ValueError('INLINE_PROFILE_ROWS_REQUIRED')
        for row in rows:
            if type(row) is not list or len(row) != length:
                raise ValueError('INLINE_PROFILE_ROW_SHAPE_REQUIRED')
            inspect_fields(row[6], 'local_null_declarations')
    profile = 'cps.compact-cached-xls.inline-null-reasons.v1' if compact.get('source',{}).get('kind')=='cached_xls' else PROFILE_ID
    return {'profile': profile, 'reasons_dictionary_empty': True, **counts,
            'null_explanations_synthesized': 0, 'input_mutations': 0}
