"""The real-song importer must not certify data or leak groups across splits."""
import csv
import importlib.util
import json
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
