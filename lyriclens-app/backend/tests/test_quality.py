import hashlib
import json
import wave
from pathlib import Path
import pytest
from lyriclens.benchmark import annotation, digest
from lyriclens.quality import audit, stress, report, CONDITIONS


def manifest(tmp_path, rows):
    target = tmp_path/'manifest.jsonl'
    target.write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')
    return target


def clip(tmp_path, identifier='one', split='development', reviewed=False, synthetic=False, group=None):
    audio = tmp_path/f'{identifier}.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(bytes(96000))
    row = dict(id=identifier, path=audio.name, sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
               duration=3, language='pt', reference='', reference_source='owned silence control',
               permissions='owned test fixture', split=split, language_switching=False,
               group_id=group or identifier, conditions={'synthetic': synthetic})
    if reviewed:
        row['review'] = dict(status='verified', reviewer='unit-test-fixture', listened=True,
                             text_permission_checked=True, annotation_sha256=digest(annotation(row)))
    return row


def test_coverage_requires_current_review_and_excludes_synthetic(tmp_path):
    rows = [clip(tmp_path, 'pending'), clip(tmp_path, 'real', reviewed=True),
            clip(tmp_path, 'synthetic', reviewed=True, synthetic=True)]
    result = audit(manifest(tmp_path, rows))
    assert result['reviewed'] == 2 and result['pending'] == 1
    assert result['coverage']['development']['language_groups']['pt'] == 1
    assert result['synthetic_clips'] == 1 and not result['ready_for_representative_comparison']
    rows[1]['reference'] = 'changed annotation'
    assert audit(manifest(tmp_path, rows))['reviewed'] == 1


def test_coverage_counts_independent_groups_and_flags_split_leakage(tmp_path):
    first = clip(tmp_path, 'one', reviewed=True, group='same-song')
    second = clip(tmp_path, 'two', reviewed=True, group='same-song')
    result = audit(manifest(tmp_path, [first, second]))
    assert result['coverage']['development']['language_groups']['pt'] == 1
    second['split'] = 'final'
    result = audit(manifest(tmp_path, [first, second]))
    assert any('leakage' in gap for gap in result['gaps'])


def test_full_coverage_requires_every_language_condition_and_final_split(tmp_path):
    from lyriclens.config import LANGUAGES
    rows = []
    for split in ('development', 'final'):
        for language in LANGUAGES:
            row = clip(tmp_path, split+language, split=split)
            # Unit-test metadata only; not a claim about real recordings.
            row.update(language=language, language_switching=True, conditions={key: True for key in CONDITIONS})
            # Different bytes ensure no hash leakage between fixtures.
            audio = tmp_path/row['path']
            audio.write_bytes(audio.read_bytes()+row['id'].encode())
            row['sha256'] = hashlib.sha256(audio.read_bytes()).hexdigest()
            row['review'] = dict(status='verified', reviewer='unit-test-fixture', listened=True,
                                 text_permission_checked=True, annotation_sha256=digest(annotation(row)))
            rows.append(row)
    assert audit(manifest(tmp_path, rows), minimum=1)['ready_for_representative_comparison']
    assert not audit(manifest(tmp_path, rows), minimum=2)['ready_for_representative_comparison']
    from lyriclens.benchmark import plan
    with pytest.raises(ValueError, match='coverage is incomplete'):
        plan(tmp_path/'manifest.jsonl', tmp_path/'incomplete.json', 'development', ['configured'], ['manual'], 'cpu', 'int8', representative=True)
    frozen = plan(tmp_path/'manifest.jsonl', tmp_path/'ready.json', 'development', ['configured'], ['manual'], 'cpu', 'int8', representative=True, minimum_groups=1)
    assert frozen['representative_coverage']['minimum_independent_groups'] == 1


def test_stress_is_reproducible_pending_review_and_preserves_reference_multiplicity(tmp_path):
    row = clip(tmp_path, reviewed=True)
    source = manifest(tmp_path, [row])
    from lyriclens.evaluate import load_manifest
    outputs = []
    for directory in (tmp_path/'a', tmp_path/'b'):
        result = stress(source, directory, ['one'], ['noise', 'repeated', 'long_repeated'])
        data = load_manifest(Path(result['manifest']))
        assert all('review' not in entry for entry in data)
        assert all(entry['conditions']['synthetic'] for entry in data)
        assert all(entry['source_sha256'] == row['sha256'] for entry in data)
        assert data[-1]['duration'] >= 120 and not data[-1]['conditions'].get('full_song')
        outputs.append([entry['sha256'] for entry in data])
    assert outputs[0] == outputs[1]
    with pytest.raises(ValueError):
        stress(source, tmp_path/'a', ['one'], ['noise'])
    row['split'] = 'final'
    with pytest.raises(ValueError):
        stress(manifest(tmp_path, [row]), tmp_path/'final', ['one'], ['noise'])


def test_condition_report_pairs_successes_and_reports_all_failures(tmp_path):
    paths = []
    for index in range(2):
        rows = []
        for identifier in ('one', 'two'):
            row = dict(id=identifier, pipeline='direct', sha256=identifier, reference='private reference',
                       language='pt', language_switching=False, split='development', duration=3,
                       conditions=dict(synthetic=True, robustness_variant='noise'),
                       state='failed' if index == 0 and identifier == 'two' else 'completed',
                       metrics=dict(character_errors=index+1, reference_characters=10, cer=(index+1)/10))
            rows.append(row)
        path = tmp_path/f'{index}.json'
        path.write_text(json.dumps(dict(split='development', per_clip=rows)), encoding='utf-8')
        paths.append(path)
    result = report(paths)
    cells = result['per_condition'][0]['models']
    assert cells[0]['attempted'] == 2 and cells[0]['completed'] == 1
    assert all(cell['paired_clips'] == 1 for cell in cells)
    assert [cell['micro_cer'] for cell in cells] == [.1, .2]
    assert 'private reference' not in json.dumps(result)
