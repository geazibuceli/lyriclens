"""The real-song importer must not certify data or leak groups across splits."""
import csv
import importlib.util
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'real_song_collection', Path(__file__).resolve().parents[2] / 'scripts/prepare_real_song_benchmark.py')
collection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collection)


def recording(tmp_path, name='audio.wav', frames=16000):
    path = tmp_path / name
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(bytes(frames * 2))
    return path.name


def row(tmp_path, **updates):
    reference = tmp_path / 'reference.txt'
    reference.write_text('Original words', encoding='utf-8')
    value = dict(id='own-song', group_id='session-one', language='en', split='development',
                 audio_path=recording(tmp_path), reference_path=reference.name,
                 reference_source='Original text by fixture author', permissions='Owned test fixture',
                 **{key: 'false' for key in collection.CONDITIONS})
    value.update(updates)
    return value


def write_csv(tmp_path, rows):
    path = tmp_path / 'collection.csv'
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_prepares_pending_review_with_hash_and_absolute_path(tmp_path):
    source = write_csv(tmp_path, [row(tmp_path)])
    output = tmp_path / 'manifest.jsonl'
    assert collection.prepare(source, output) == 1
    clip = json.loads(output.read_text(encoding='utf-8'))
    assert clip['review']['status'] == 'pending'
    assert clip['review']['listened'] is False
    assert clip['duration'] == 1
    assert len(clip['sha256']) == 64
    assert Path(clip['path']).is_absolute()
    with pytest.raises(ValueError, match='already exists'):
        collection.prepare(source, output)


@pytest.mark.parametrize('field', ['permissions', 'reference_source', 'group_id', 'audio_path'])
def test_rejects_unfilled_collection_slots(tmp_path, field):
    source = write_csv(tmp_path, [row(tmp_path, **{field: ''})])
    output = tmp_path / 'manifest.jsonl'
    with pytest.raises(ValueError, match=f'fill {field}'):
        collection.prepare(source, output)
    assert not output.exists()


@pytest.mark.parametrize('same_group', [True, False])
def test_rejects_cross_split_leakage(tmp_path, same_group):
    first = row(tmp_path)
    second = {**first, 'id': 'second', 'split': 'final', 'group_id': 'session-one' if same_group else 'other-session'}
    if same_group:
        second['audio_path'] = recording(tmp_path, 'different.wav', frames=32000)
    source = write_csv(tmp_path, [first, second])
    with pytest.raises(ValueError, match='cannot span'):
        collection.prepare(source, tmp_path / 'manifest.jsonl')


def test_requires_explicit_condition_labels(tmp_path):
    source = write_csv(tmp_path, [row(tmp_path, full_song='maybe')])
    with pytest.raises(ValueError, match='true or false'):
        collection.prepare(source, tmp_path / 'manifest.jsonl')


def test_check_lists_all_problems_without_reference_text(tmp_path):
    first = row(tmp_path, permissions='', full_song='maybe')
    second = {**first, 'id': 'second', 'permissions': 'Owned',
              'audio_path': 'missing.wav', 'reference_path': 'missing.txt'}
    report, rows = collection.inspect_collection(write_csv(tmp_path, [first, second]))
    assert rows == []
    assert report['slots'] == report['invalid_slots'] == 2
    assert [issue['line'] for issue in report['issues']] == [2, 3]
    assert len(report['issues'][0]['problems']) == 2
    assert any('PCM WAV' in problem for problem in report['issues'][1]['problems'])
    assert any('UTF-8 reference' in problem for problem in report['issues'][1]['problems'])
    assert 'Original words' not in json.dumps(report)
    assert report['ready_for_import'] is False


def test_check_counts_independent_groups_but_never_certifies_review(tmp_path):
    first = row(tmp_path, full_song='true')
    second = {**first, 'id': 'second'}
    report, rows = collection.inspect_collection(write_csv(tmp_path, [first, second]))
    assert report['ready_for_import'] is True
    assert report['valid_recordings'] == 2
    coverage = report['coverage']['development']
    assert coverage['language_groups']['en'] == 1
    assert coverage['condition_groups']['full_song'] == 1
    assert report['human_review_required'] is True
    assert report['ready_for_representative_comparison'] is False
    assert all(row['review']['status'] == 'pending' for row in rows)


@pytest.mark.parametrize('contents', ['', 'id\n'])
def test_check_rejects_empty_or_missing_columns(tmp_path, contents):
    source = tmp_path / 'empty.csv'
    source.write_text(contents, encoding='utf-8')
    report, _ = collection.inspect_collection(source)
    assert report['ready_for_import'] is False
    assert any('Missing CSV columns' in problem
               for issue in report['issues'] for problem in issue['problems'])


def test_check_rejects_duplicate_ids(tmp_path):
    first = row(tmp_path)
    report, _ = collection.inspect_collection(write_csv(tmp_path, [first, first]))
    assert report['ready_for_import'] is False
    assert any('Duplicate' in problem for problem in report['issues'][0]['problems'])


def test_check_rejects_invalid_reference_encoding(tmp_path):
    first = row(tmp_path)
    (tmp_path / first['reference_path']).write_bytes(b'\xff\xff')
    report, _ = collection.inspect_collection(write_csv(tmp_path, [first]))
    assert report['ready_for_import'] is False
    assert any('UTF-8' in problem for problem in report['issues'][0]['problems'])


def test_check_cli_reports_pending_slots_without_creating_manifest(tmp_path):
    source = write_csv(tmp_path, [row(tmp_path, permissions='')])
    report = tmp_path / 'check.json'
    command = [sys.executable, str(Path(collection.__file__)), str(source),
               '--check', '--report', str(report)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(report.read_text(encoding='utf-8'))['invalid_slots'] == 1
    assert not (tmp_path / 'manifest.jsonl').exists()
    contents = report.read_bytes()
    repeated = subprocess.run(command, capture_output=True, text=True)
    assert repeated.returncode == 1
    assert report.read_bytes() == contents


def test_check_cli_passes_valid_collection_with_review_still_required(tmp_path):
    source = write_csv(tmp_path, [row(tmp_path)])
    result = subprocess.run([sys.executable, str(Path(collection.__file__)),
                             str(source), '--check'], capture_output=True, text=True)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report['ready_for_import'] is True
    assert report['ready_for_representative_comparison'] is False
