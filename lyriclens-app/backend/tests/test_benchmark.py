import hashlib
import json
import pytest
from lyriclens.benchmark import prepare, approve, checked, export, compare, read_queue, plan, run
from lyriclens.evaluate import load_manifest


def fixture(tmp_path):
    audio = tmp_path/'audio.wav'
    audio.write_bytes(b'owned fixture')
    manifest = tmp_path/'source.jsonl'
    row = dict(id='one', path='audio.wav', sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
               language='pt', reference='Texto de teste', reference_source='own text',
               permissions='owned test audio and text', duration=3, conditions={'kind':'singing'},
               language_switching=False, split='development')
    manifest.write_text(json.dumps(row)+'\n', encoding='utf-8')
    queue = tmp_path/'review.json'
    prepare(manifest, queue)
    return queue


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def test_review_gate_snapshot_and_audio_integrity(tmp_path):
    queue = fixture(tmp_path)
    data = read_queue(queue)
    assert not checked(data['clips'][0])
    with pytest.raises(ValueError):
        export(queue, tmp_path/'manifest.jsonl')
    with pytest.raises(ValueError):
        approve(queue, 'one', 'reviewer')
    data['clips'][0]['group_id'] = 'song-session-one'
    write(queue, data)
    approve(queue, 'one', 'human-fixture')
    result = export(queue, tmp_path/'manifest.jsonl')
    assert result['coverage']['development']['pt'] == 1
    assert result['coverage']['final']['ja'] == 0
    assert len(load_manifest(tmp_path/'manifest.jsonl', require_reviewed=True)) == 1
    data = read_queue(queue)
    data['clips'][0]['reference'] += ' alterado'
    write(queue, data)
    assert not checked(data['clips'][0])
    with pytest.raises(ValueError):
        export(queue, tmp_path/'new.jsonl')
    (tmp_path/'audio.wav').write_bytes(b'changed')
    with pytest.raises(ValueError):
        approve(queue, 'one', 'human-fixture')


@pytest.mark.parametrize('shared', ['audio', 'group'])
def test_split_leakage_is_rejected(tmp_path, shared):
    queue = fixture(tmp_path)
    data = read_queue(queue)
    first = data['clips'][0]
    first['group_id'] = 'one'
    second = {**first, 'id': 'two', 'split': 'final', 'group_id': 'two' if shared == 'audio' else 'one'}
    if shared == 'group':
        other = tmp_path/'other.wav'
        other.write_bytes(b'other fixture')
        second.update(path=str(other), sha256=hashlib.sha256(other.read_bytes()).hexdigest())
    data['clips'].append(second)
    write(queue, data)
    for identifier in ('one', 'two'):
        approve(queue, identifier, 'human-fixture')
    with pytest.raises(ValueError, match='leakage'):
        export(queue, tmp_path/'manifest.jsonl')


def test_compare_rejects_unpaired_references_and_preserves_failures(tmp_path):
    row = dict(id='one', pipeline='direct', sha256='hash', reference='Olá', language='pt',
               conditions={}, language_switching=False, split='development', state='completed', metrics={'cer':.5})
    baseline, candidate = tmp_path/'a.json', tmp_path/'b.json'
    write(baseline, dict(split='development', per_clip=[row]))
    write(candidate, dict(split='development', per_clip=[{**row, 'metrics':{'cer':.25}}]))
    assert compare(baseline, candidate)['pairs'][0]['cer_delta'] == -.25
    write(candidate, dict(split='development', per_clip=[{**row, 'state':'failed'}]))
    assert compare(baseline, candidate)['pairs'][0]['cer_delta'] is None
    write(candidate, dict(split='development', per_clip=[{**row, 'reference':'different'}]))
    with pytest.raises(ValueError, match='not paired'):
        compare(baseline, candidate)


def test_prepare_refuses_overwrite_and_strict_manifest_rejects_pending(tmp_path):
    queue = fixture(tmp_path)
    with pytest.raises(ValueError):
        prepare(tmp_path/'source.jsonl', queue)
    with pytest.raises(ValueError, match='review'):
        load_manifest(tmp_path/'source.jsonl', require_reviewed=True)


def test_protocol_freezes_config_rejects_tampering_and_limits_final(tmp_path):
    queue = fixture(tmp_path)
    data = read_queue(queue)
    data['clips'][0]['group_id'] = 'song'
    write(queue, data)
    approve(queue, 'one', 'human-fixture')
    manifest = tmp_path/'checked.jsonl'
    export(queue, manifest)
    protocol = tmp_path/'protocol.json'
    frozen = plan(manifest, protocol, 'development', ['configured'], ['auto'], 'cpu', 'int8')
    assert frozen['coverage']['pt'] == 1
    assert frozen['models']['configured']['revision']
    frozen['device'] = 'cuda'
    write(protocol, frozen)
    with pytest.raises(ValueError, match='Protocol changed'):
        run(protocol)
    with pytest.raises(ValueError, match='No reviewed'):
        plan(manifest, tmp_path/'final.json', 'final', ['configured'], ['auto'], 'cpu', 'int8')
    data = read_queue(queue)
    data['clips'][0]['split'] = 'final'
    write(queue, data)
    approve(queue, 'one', 'human-fixture')
    final = tmp_path/'final.jsonl'
    export(queue, final)
    with pytest.raises(ValueError, match='Choose one'):
        plan(final, tmp_path/'final.json', 'final', ['configured','large-v3'], ['auto'], 'cpu', 'int8')


def test_protocol_runner_builds_isolated_commands_and_paired_report(tmp_path, monkeypatch):
    import subprocess
    queue = fixture(tmp_path)
    data = read_queue(queue)
    data['clips'][0]['group_id'] = 'song'
    write(queue, data)
    approve(queue, 'one', 'human-fixture')
    manifest = tmp_path/'checked.jsonl'
    export(queue, manifest)
    protocol = tmp_path/'protocol.json'
    plan(manifest, protocol, 'development', ['configured'], ['auto','manual'], 'cpu', 'int8')
    calls = []
    def fake_run(command, check):
        calls.append(command)
        rows = load_manifest(manifest)
        row = {k:v for k,v in rows[0].items() if k != 'resolved_path'}
        report = dict(split='development', per_clip=[dict(row, pipeline='direct', state='completed', metrics={'cer':.2})])
        write(Path(command[command.index('--output')+1]), report)
        return subprocess.CompletedProcess(command, 0)
    from pathlib import Path
    monkeypatch.setattr(subprocess, 'run', fake_run)
    run(protocol)
    assert len(calls) == 2 and all('--require-reviewed' in call for call in calls)
    assert '--manual-language' in calls[1]
    assert (tmp_path/'protocol.runs/compare-configured-manual.json').exists()
    with pytest.raises(FileExistsError):
        run(protocol)
