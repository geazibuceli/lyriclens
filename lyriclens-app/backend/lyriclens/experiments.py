"""Screen decoding experiments against paired baseline recordings."""


def screen(reports):
    variants = {}
    for row in reports:
        key = (row['id'], row['pipeline'])
        index = variants.setdefault(row['variant'], {})
        if key in index:
            raise ValueError('Duplicate experiment row')
        index[key] = row
    if 'baseline' not in variants:
        return []
    baseline = variants.pop('baseline')
    decisions = []
    for variant, candidate in variants.items():
        if candidate.keys() != baseline.keys():
            raise ValueError('Candidate and baseline must contain the same recordings and routes')
        for key, old in baseline.items():
            if any(old[field] != candidate[key][field] for field in ('sha256', 'language')):
                raise ValueError('Candidate and baseline inputs differ')
        groups = []
        for language, pipeline in sorted({(r['language'], r['pipeline']) for r in baseline.values()}):
            keys = [key for key, row in baseline.items() if (row['language'], row['pipeline']) == (language, pipeline)]
            paired = [key for key in keys if baseline[key]['state'] == candidate[key]['state'] == 'completed']
            characters = sum(baseline[key]['metrics']['reference_characters'] for key in paired)
            if any(baseline[key]['metrics']['reference_characters'] != candidate[key]['metrics']['reference_characters'] for key in paired):
                raise ValueError('Reference character denominators differ')
            old_errors = sum(baseline[key]['metrics']['character_errors'] for key in paired)
            new_errors = sum(candidate[key]['metrics']['character_errors'] for key in paired)
            recovered = sum(baseline[key]['state'] != 'completed' and candidate[key]['state'] == 'completed' for key in keys)
            lost = sum(baseline[key]['state'] == 'completed' and candidate[key]['state'] != 'completed' for key in keys)
            groups.append(dict(language=language, pipeline=pipeline, attempted=len(keys), paired_clips=len(paired),
                               reference_characters=characters, recovered_clips=recovered, lost_clips=lost,
                               baseline_cer=old_errors/characters if characters else None,
                               candidate_cer=new_errors/characters if characters else None,
                               character_error_delta=new_errors-old_errors))
        regressions = [g for g in groups if g['lost_clips'] or g['character_error_delta'] > 0]
        improvements = [g for g in groups if g['recovered_clips'] or g['character_error_delta'] < 0]
        decisions.append(dict(variant=variant, groups=groups,
                              eligible_for_further_validation=bool(improvements) and not regressions,
                              interpretation='Development screening only. Compare shared successes; recovered clips are not an accuracy gain. '
                                             'Any lost clip or increased character errors in a language/route blocks eligibility. '
                                             'No automatic runtime change; independent reviewed validation is required.'))
    return decisions
