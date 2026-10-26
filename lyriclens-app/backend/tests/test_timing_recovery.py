import wave
import time
from dataclasses import dataclass
from dataclasses import replace
import pytest
from lyriclens.adapters import WhisperTranscriber
from lyriclens.config import Settings
from lyriclens.domain import validate_model_segments


@dataclass
class Segment:
    start: float
    end: float
    text: str = 'test'


@dataclass
class Info:
    language: str = 'pt'
    language_probability: float = .9


def adapter(tmp_path, responses, aligned=False):
    settings = replace(Settings(root=tmp_path/'data'), word_timestamps=aligned)
    settings.model_dir.mkdir(parents=True)
    (settings.model_dir/'READY.json').write_text('{}')
    audio = tmp_path/'audio.wav'
    with wave.open(str(audio), 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x01\x00' * 48000)
    calls = []

    class Model:
        def transcribe(self, path, **kwargs):
            calls.append(kwargs)
            response = responses[len(calls)-1]
            if isinstance(response, Exception):
                raise response
            return iter(response), Info()

    transcriber = WhisperTranscriber(settings)
    transcriber.model = Model()
    return transcriber, audio, calls


def test_invalid_timing_retries_same_model_once_and_preserves_first_response(tmp_path):
    transcriber, audio, calls = adapter(tmp_path, [[Segment(0, 4)], [Segment(.1, 2.9)]])
    raw = transcriber.transcribe(audio, 'pt')
    assert len(calls) == 2
    assert calls[0]['word_timestamps'] is False and calls[1]['word_timestamps'] is True
    assert calls[0]['language'] == calls[1]['language'] == 'pt'
    assert {k:v for k,v in calls[0].items() if k != 'word_timestamps'} == {k:v for k,v in calls[1].items() if k != 'word_timestamps'}
    assert raw['timing_recovery']['succeeded']
    assert raw['timing_recovery']['initial_response']['segments'][0]['end'] == 4
    assert raw['segments'][0]['end'] == 2.9
    assert transcriber.settings.word_timestamps is False


@pytest.mark.parametrize('segments', [[], [Segment(0, 2)], [Segment(2, 3), Segment(0, 1)]])
def test_valid_empty_and_unordered_output_never_retry(tmp_path, segments):
    transcriber, audio, calls = adapter(tmp_path, [segments])
    raw = transcriber.transcribe(audio, None)
    assert len(calls) == 1 and 'timing_recovery' not in raw


def test_invalid_aligned_output_does_not_retry_or_clamp(tmp_path):
    transcriber, audio, calls = adapter(tmp_path, [[Segment(0, 4)]], aligned=True)
    raw = transcriber.transcribe(audio, 'pt')
    assert len(calls) == 1
    with pytest.raises(ValueError):
        validate_model_segments(raw['segments'], 3)


def test_gap_protection_passes_native_option_without_enabling_vad(tmp_path):
    transcriber, audio, calls = adapter(tmp_path, [[Segment(.2, 2.8)]], aligned=True)
    transcriber.settings = replace(transcriber.settings, hallucination_silence_threshold=2.0)
    raw = transcriber.transcribe(audio, 'en')
    assert len(calls) == 1
    assert calls[0]['hallucination_silence_threshold'] == 2.0
    assert calls[0]['word_timestamps'] is True
    assert calls[0]['vad_filter'] is False
    assert raw['segments'] == [{'start': .2, 'end': 2.8, 'text': 'test'}]


def test_invalid_text_does_not_trigger_timing_retry(tmp_path):
    transcriber, audio, calls = adapter(tmp_path, [[Segment(0, 2, 'x' * 20001)]])
    raw = transcriber.transcribe(audio, 'pt')
    assert len(calls) == 1 and 'timing_recovery' not in raw


@pytest.mark.parametrize('second', [[Segment(0, 5)], RuntimeError('private/model/path')])
def test_failed_recovery_still_fails_validation_and_keeps_initial_raw(tmp_path, second):
    transcriber, audio, calls = adapter(tmp_path, [[Segment(0, 4)], second])
    raw = transcriber.transcribe(audio, 'pt')
    assert len(calls) == 2 and not raw['timing_recovery']['succeeded']
    assert raw['timing_recovery']['initial_response']['segments'][0]['end'] == 4
    assert 'private/model/path' not in str(raw)
    with pytest.raises(ValueError):
        validate_model_segments(raw['segments'], 3)


@pytest.mark.parametrize('recoverable', [True, False])
def test_job_exposes_attempts_and_recovery_provenance(tmp_path, recoverable):
    from fastapi.testclient import TestClient
    from lyriclens.api import create_app
    transcriber, audio, calls = adapter(tmp_path, [[Segment(0, 4)], [Segment(0, 2 if recoverable else 5)]])

    class Decoder:
        def decode(self, source, target):
            target.write_bytes(source.read_bytes())
            return {'duration': 3}

    app = create_app(transcriber.settings, Decoder(), transcriber)
    with TestClient(app) as client:
        response = client.post('/api/jobs', files={'file': ('clip.wav', audio.read_bytes(), 'audio/wav')})
        assert response.status_code == 202
        path = '/api/jobs/' + response.json()['id']
        for _ in range(100):
            job = client.get(path).json()
            if job['state'] not in ('queued', 'processing'):
                break
            time.sleep(.01)
        assert job['state'] == ('completed' if recoverable else 'failed')
        raw = client.get(path + '/raw').json()
        assert raw['timing_recovery']['initial_response']['segments'][0]['end'] == 4
        assert raw['timing_recovery']['succeeded'] == recoverable
        assert len(calls) == 2
        if recoverable:
            result = job['results']['direct']
            assert any('native-alignment retry' in warning for warning in result['warnings'])
            assert result['provenance']['timing_recovery']['effective_settings']['word_timestamps']
            assert not job['inference']['word_timestamps']
