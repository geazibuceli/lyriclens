"""Publisher download preparation must preserve attribution and pending review."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'open_song_pilot', Path(__file__).resolve().parents[2] / 'scripts/prepare_open_song_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def page(title, **changes):
    song = {'@type': 'MusicRecording', 'name': title, 'license': pilot.LICENSE,
            'byArtist': {'name': 'Josh Woodward'},
            'recordingOf': {'lyrics': {'text': 'Publisher words\r\nChorus'}}}
    song.update(changes)
    return ('<script type="application/ld+json">' + json.dumps(song) + '</script>'
            '<audio src="https://www.joshwoodward.com/mp3/TheWake/original.mp3"></audio>')


def test_reads_publisher_lyrics_without_inventing_repeated_words():
    url, lyrics = pilot.parse_song(page('Hollow Grove'), 'Hollow Grove')
    assert url.endswith('/original.mp3')
    assert lyrics == 'Publisher words\nChorus'


@pytest.mark.parametrize('changes', [
    {'license': 'https://creativecommons.org/licenses/by-nc/4.0/'},
    {'byArtist': {'name': 'Unrelated uploader'}},
    {'recordingOf': {}},
    {'name': 'Unrelated song'},
])
def test_rejects_changed_license_identity_or_missing_lyrics(changes):
    with pytest.raises(ValueError):
        pilot.parse_song(page('Hollow Grove', **changes), 'Hollow Grove')


@pytest.mark.parametrize('replacement', [
    'https://unrelated.example/original.mp3',
    'https://www.joshwoodward.com/mp3/TheWake/NoVox-original.mp3',
])
def test_rejects_unexpected_or_instrumental_audio(replacement):
    html = page('Hollow Grove').replace(
        'https://www.joshwoodward.com/mp3/TheWake/original.mp3', replacement)
    with pytest.raises(ValueError, match='original vocal MP3'):
        pilot.parse_song(html, 'Hollow Grove')


def test_prepares_local_evidence_without_claiming_human_review(tmp_path, monkeypatch):
    def fetch(url, target, limit):
        if target.suffix == '.html' and url != pilot.FAQ:
            title = next(title for slug, title in pilot.SONGS if url.endswith(slug))
            data = page(title).encode()
        else:
            data = b'Local test fixture; no network'
        target.write_bytes(data)
        return dict(url=url, path=target.name, bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest())

    class Decoder:
        def __init__(self, settings):
            pass

        def decode(self, source, target):
            target.write_bytes(b'Decoded fixture')
            return {'duration': 180}

    monkeypatch.setattr(pilot, 'fetch', fetch)
    monkeypatch.setattr(pilot, 'FFmpegDecoder', Decoder)
    output = tmp_path / 'pilot'
    provenance = pilot.prepare(output)
    assert provenance['independent_groups'] == 1
    assert provenance['human_review_required'] is True
    assert len(provenance['evidence']) == 7
    queue = json.loads((output / 'review.json').read_text(encoding='utf-8'))
    assert len(queue['clips']) == 3
    for row in queue['clips']:
        assert Path(row['path']).is_file()
        assert row['split'] == 'development'
        assert row['review']['status'] == 'pending'
        assert row['review']['listened'] is False
        assert row['review']['text_permission_checked'] is False
        assert row['reference'] == 'Publisher words\nChorus'
        assert 'annotation_sha256' not in row['review']
    assert 'Josh Woodward' in (output / 'ATTRIBUTION.txt').read_text(encoding='utf-8')
    before = (output / 'review.json').read_bytes()
    with pytest.raises(FileExistsError):
        pilot.prepare(output)
    assert (output / 'review.json').read_bytes() == before


def test_smoke_checks_timestamps_and_continues_after_failure(tmp_path, monkeypatch):
    smoke_spec = importlib.util.spec_from_file_location(
        'full_song_smoke', Path(__file__).resolve().parents[2] / 'scripts/run_full_song_smoke.py')
    smoke = importlib.util.module_from_spec(smoke_spec)
    smoke_spec.loader.exec_module(smoke)
    manifest = tmp_path / 'manifest.jsonl'
    manifest.write_text('fixture', encoding='utf-8')
    rows = [dict(id='fixture-song', group_id='fixture-group', sha256='fixture-hash',
                 path='fixture.wav', resolved_path=tmp_path / 'fixture.wav', language='en',
                 split='development', duration=180, conditions={'full_song': True})]

    class Transcriber:
        def __init__(self, settings):
            self.model_id = settings.model_id

        def transcribe(self, audio, language):
            if 'small' in self.model_id:
                return dict(segments=[dict(start=0, end=200, text='Invalid timestamp')])
            return dict(segments=[dict(start=1, end=3, text='Private recognized words')], model_executed=True)

    monkeypatch.setattr(smoke, 'WhisperTranscriber', Transcriber)
    monkeypatch.setattr(smoke, 'load_manifest', lambda _: rows)
    monkeypatch.setattr(smoke, 'environment', lambda: {})
    output = tmp_path / 'inference'
    report = smoke.run(manifest, output)
    assert report['attempted'] == 2
    assert report['completed'] == 1
    assert report['per_run'][0]['state'] == 'failed'
    assert report['per_run'][1]['segments'] == 1
    assert report['per_run'][1]['empty_output'] is False
    assert report['accuracy_scored'] is False
    serialized = (output / 'summary.json').read_text(encoding='utf-8')
    assert 'Private recognized words' not in serialized
    assert 'metrics' not in serialized
    assert report['human_review_required'] is True
    with pytest.raises(FileExistsError):
        smoke.run(manifest, output)


@pytest.mark.parametrize('failure', [None, 'separation', 'timeline'])
def test_paired_smoke_reuses_isolation_and_keeps_direct_results(tmp_path, monkeypatch, failure):
    smoke_spec = importlib.util.spec_from_file_location(
        'paired_smoke', Path(__file__).resolve().parents[2] / 'scripts/run_full_song_smoke.py')
    smoke = importlib.util.module_from_spec(smoke_spec)
    smoke_spec.loader.exec_module(smoke)
    manifest = tmp_path / 'manifest.jsonl'
    manifest.write_text('fixture', encoding='utf-8')
    source = tmp_path / 'original.wav'
    source.write_bytes(b'original')
    rows = [dict(id='song', group_id='session', sha256=hashlib.sha256(b'original').hexdigest(),
                 resolved_path=source, language='en', split='development', duration=180,
                 conditions={'full_song': True})]
    isolated = []
    closed = []
    recognized = []

    class Separator:
        def __init__(self, settings):
            pass

        def separate(self, audio, directory):
            isolated.append(audio)
            if failure == 'separation':
                raise ValueError('Isolation failed')
            return audio

        def close(self):
            closed.append(True)

    class Decoder:
        def __init__(self, settings):
            pass

        def decode(self, original, target):
            target.write_bytes(b'isolated vocals')
            return {'duration': 179 if failure == 'timeline' else 180}

    class Transcriber:
        def __init__(self, settings):
            pass

        def transcribe(self, audio, language):
            recognized.append(audio.read_bytes())
            return dict(segments=[dict(start=1, end=3, text='Private words')], model_executed=True)

    monkeypatch.setattr(smoke, 'load_manifest', lambda _: rows)
    monkeypatch.setattr(smoke, 'environment', lambda: {})
    monkeypatch.setattr(smoke, 'DemucsSeparator', Separator)
    monkeypatch.setattr(smoke, 'FFmpegDecoder', Decoder)
    monkeypatch.setattr(smoke, 'WhisperTranscriber', Transcriber)
    report = smoke.run(manifest, tmp_path / 'out', pipelines=('direct', 'vocals'))
    assert len(isolated) == len(closed) == 1
    assert report['attempted'] == 4
    assert report['completed'] == (2 if failure else 4)
    if not failure:
        assert recognized == [b'original', b'isolated vocals'] * 2
        vocals = [row for row in report['per_run'] if row['pipeline'] == 'vocals']
        assert vocals[0]['recognition_audio_sha256'] == vocals[1]['recognition_audio_sha256']
    else:
        assert recognized == [b'original', b'original']
        assert all(row['state'] == 'failed' for row in report['per_run'] if row['pipeline'] == 'vocals')
    assert 'Private words' not in json.dumps(report)
    assert report['accuracy_scored'] is False
    summary_spec = importlib.util.spec_from_file_location(
        'route_summary', Path(__file__).resolve().parents[2] / 'scripts/summarize_full_song_routes.py')
    summary_module = importlib.util.module_from_spec(summary_spec)
    summary_spec.loader.exec_module(summary_module)
    summary_path = tmp_path / 'out' / 'summary.json'
    comparison = summary_module.summarize(summary_path)
    assert len(comparison['paired_comparisons']) == 2
    assert 'Private words' not in json.dumps(comparison)
    assert all(pair['completed_pair'] is (failure is None) for pair in comparison['paired_comparisons'])
    if not failure:
        assert comparison['paired_comparisons'][0]['same_normalized_text'] is True
        assert comparison['paired_comparisons'][0]['vocals']['review_signals']['long_passages'] == 0
    report['per_run'][1]['audio_sha256'] = 'different audio'
    summary_path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError, match='Unpaired inputs'):
        summary_module.summarize(summary_path)
