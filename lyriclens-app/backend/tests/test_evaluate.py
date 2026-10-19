import json
import sys
import pytest
from lyriclens import evaluate


@pytest.mark.parametrize('failure', [None, 'bounds', 'recognition'])
def test_evaluation_matches_runtime_order_preserves_raw_and_records_stages(tmp_path, monkeypatch, failure):
    manifest = tmp_path/'manifest.jsonl'
    manifest.write_text('fixture', encoding='utf-8')
    output = tmp_path/'report.json'
    row = dict(id='clip', resolved_path=tmp_path/'audio.wav', duration=3, language='pt',
               reference='primeiro depois', split='development', language_switching=False)
    emitted = [{'start': 2, 'end': 4 if failure == 'bounds' else 3, 'text': 'depois'},
               {'start': 0, 'end': 1, 'text': 'primeiro'}]

    class Decoder:
        def decode(self, source, target):
            return {'duration': 3}

    class Model:
        def transcribe(self, audio, language):
            assert language == 'pt'
            if failure == 'recognition':
                raise ValueError('recognition failed')
            return {'segments': emitted}

    class Separator:
        process = None
        def separate(self, audio, directory):
            return audio
        def close(self):
            pass

    monkeypatch.setattr(evaluate, 'load_manifest', lambda *args, **kwargs: [row])
    monkeypatch.setattr(evaluate, 'FFmpegDecoder', lambda settings: Decoder())
    monkeypatch.setattr(evaluate, 'WhisperTranscriber', lambda settings: Model())
    monkeypatch.setattr(evaluate, 'DemucsSeparator', lambda settings: Separator())
    monkeypatch.setattr(sys, 'argv', ['evaluate', str(manifest), '--split', 'development',
                                    '--manual-language', '--output', str(output)])
    evaluate.main()
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['language_mode'] == 'manual'
    for result in report['per_clip']:
        assert set(result['stage_seconds']) == ({'decode', 'recognition'} if result['pipeline'] == 'direct'
                                               else {'decode', 'separation', 'recognition'})
        assert all(seconds >= 0 for seconds in result['stage_seconds'].values())
        assert result['state'] == ('failed' if failure else 'completed')
        if failure != 'recognition':
            assert result['raw']['segments'] == emitted
        if not failure:
            assert result['timestamp_order_normalized']
            assert result['hypothesis'] == 'primeiro\ndepois'
            assert result['metrics']['cer'] == 0
