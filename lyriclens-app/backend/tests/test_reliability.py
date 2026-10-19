import io
import queue
import wave
from pathlib import Path
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from lyriclens.api import create_app
from lyriclens.config import Settings
from lyriclens import maintenance
from test_app import Decoder, Model, upload, wait
from test_translation import translate, translation_wait


def test_resume_preserves_completed_route_and_edits(tmp_path):
    class Separator:
        failed = False
        def separate(self, source, target):
            if not self.failed:
                self.failed = True
                raise ValueError('One-time separation failure')
            return source
    model = Model()
    app = create_app(Settings(root=tmp_path),Decoder(),model,Separator())
    with TestClient(app) as client:
        job = wait(client,upload(client,pipeline='both').json()['id'])
        identifier = job['id']
        assert job['results']['direct']['state'] == 'completed'
        assert job['results']['vocals']['state'] == 'failed'
        reviewed = [dict(start=.1,end=2.9,text='Saved review')]
        client.put(f'/api/jobs/{identifier}/edit',json=dict(pipeline='direct',segments=reviewed))
        path = f'/api/jobs/{identifier}/resume'
        assert client.post(path).status_code == 202
        resumed = wait(client,identifier)
        assert resumed['results']['vocals']['state'] == 'completed'
        assert resumed['results']['direct']['original'] == job['results']['direct']['original']
        assert resumed['results']['direct']['edited'] == reviewed
        assert len(model.languages) == 2  # Direct once, then only unfinished vocals.
        assert client.post(path).status_code == 409


def test_resume_queue_rollback_and_changed_recording(tmp_path,monkeypatch):
    app = create_app(Settings(root=tmp_path),Decoder(),Model())
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        identifier = job['id']
        app.state.store.update(identifier,state='interrupted',results={})
        def full(_):
            raise queue.Full
        monkeypatch.setattr(app.state.worker.queue,'put_nowait',full)
        assert client.post(f'/api/jobs/{identifier}/resume').status_code == 429
        assert client.get(f'/api/jobs/{identifier}').json()['state'] == 'interrupted'
        (tmp_path/'jobs'/identifier/'original').write_bytes(b'changed')
        assert client.post(f'/api/jobs/{identifier}/resume').status_code == 409


def test_translation_resume_from_durable_checkpoint(tmp_path):
    class Translator:
        def __init__(self):
            self.calls = []
            self.failed = False
        def translate(self,text,source,target):
            self.calls.append(text)
            if text == 'second' and not self.failed:
                self.failed = True
                raise ValueError('Temporary test failure')
            return 'translated '+text
    translator = Translator()
    app = create_app(Settings(root=tmp_path),Decoder(),Model(),translator=translator)
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        path = f"/api/jobs/{job['id']}"
        client.put(path+'/edit',json=dict(pipeline='direct',segments=[dict(start=0,end=1,text='first'),dict(start=1,end=3,text='second')]))
        assert translate(client,job['id']).status_code == 202
        _,item = translation_wait(client,job['id'])
        assert item['state'] == 'failed' and item['completed_segments'] == 1
        assert item['segments'][0]['text'] == 'translated first'
        assert client.post(path+'/translation/resume',json=dict(pipeline='direct',source_language='ko',target_language='pt')).status_code == 202
        _,item = translation_wait(client,job['id'])
        assert item['state'] == 'completed'
        assert translator.calls == ['first','second','second']
        assert len(item['segments']) == 2


def test_service_restart_recovers_translation_checkpoint(tmp_path):
    class Translator:
        def translate(self,text,source,target):
            if text == 'second':
                raise ValueError('Simulated interruption before second result')
            return 'saved first'
    settings = Settings(root=tmp_path)
    app = create_app(settings,Decoder(),Model(),translator=Translator())
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        identifier = job['id']
        path = f'/api/jobs/{identifier}'
        client.put(path+'/edit',json=dict(pipeline='direct',segments=[dict(start=0,end=1,text='first'),dict(start=1,end=3,text='second')]))
        translate(client,identifier)
        _,item = translation_wait(client,identifier)
        assert len(item['segments']) == 1
    persisted = app.state.store.get(identifier)
    persisted['translations']['direct:pt']['state'] = 'processing'
    app.state.store.put(persisted)  # Simulate persisted state at a process crash.
    from test_translation import Translator as SuccessfulTranslator
    translator = SuccessfulTranslator()
    restarted = create_app(settings,Decoder(),Model(),translator=translator)
    with TestClient(restarted) as client:
        recovered = client.get(path).json()['translations']['direct:pt']
        assert recovered['state'] == 'interrupted' and recovered['segments'][0]['text'] == 'saved first'
        assert client.post(path+'/translation/resume',json=dict(pipeline='direct',source_language='ko',target_language='pt')).status_code == 202
        _,item = translation_wait(client,identifier)
        assert item['state'] == 'completed' and len(item['segments']) == 2
        assert [text for text,_,_ in translator.calls] == ['second']


def test_cleanup_scopes_generated_cache_and_blocks_active_jobs(tmp_path):
    app = create_app(Settings(root=tmp_path),Decoder(),Model())
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        path = f"/api/jobs/{job['id']}"
        folder = tmp_path/'jobs'/job['id']
        (folder/'stems').mkdir()
        (folder/'stems'/'vocals.wav').write_bytes(b'generated')
        raw = (folder/'direct-raw.json').read_bytes()
        original = (folder/'original').read_bytes()
        assert client.get('/api/storage').json()['jobs'][0]['cache_bytes'] > 0
        app.state.store.update(job['id'],state='processing')
        assert client.post(path+'/cleanup-cache').status_code == 409
        app.state.store.update(job['id'],state='completed')
        assert client.post(path+'/cleanup-cache').json()['removed_bytes'] > 0
        assert not (folder/'decoded.wav').exists() and not (folder/'stems').exists()
        assert (folder/'direct-raw.json').read_bytes() == raw
        assert (folder/'original').read_bytes() == original
        assert client.get(path).json()['results'] == job['results']
        assert client.get('/api/storage').json()['jobs'][0]['cache_bytes'] == 0


def test_cleanup_rejects_external_links(tmp_path):
    root = tmp_path/'data'
    folder = root/'jobs'/'job'
    folder.mkdir(parents=True)
    outside = tmp_path/'outside.wav'
    outside.write_bytes(b'preserve')
    try:
        (folder/'decoded.wav').symlink_to(outside)
    except OSError:
        pytest.skip('Symlink creation requires privileges on this Windows installation')
    with pytest.raises(ValueError):
        maintenance.cleanup(Settings(root=root),'job')
    assert outside.read_bytes() == b'preserve'


def test_diagnostics_do_not_load_recognition_model(tmp_path,monkeypatch):
    import lyriclens.adapters as adapters
    def forbidden(*args,**kwargs):
        raise AssertionError('Diagnostics must not load ASR')
    monkeypatch.setattr(adapters.WhisperTranscriber,'transcribe',forbidden)
    report = maintenance.diagnostics(Settings(root=tmp_path,ffmpeg='nonexistent-test-ffmpeg'))
    assert not next(c for c in report['checks'] if c['name']=='FFmpeg')['ok']
    assert report['checks']


def test_waveform_from_owned_pcm_preserves_original(tmp_path):
    from lyriclens.config import ffmpeg_executable
    import shutil
    if not shutil.which(ffmpeg_executable()):
        pytest.skip('FFmpeg unavailable')
    buffer = io.BytesIO()
    with wave.open(buffer,'wb') as wav:
        wav.setparams((1,2,16000,0,'NONE','not compressed'))
        wav.writeframes(bytes(32000))
    app = create_app(Settings(root=tmp_path),transcriber=Model())
    with TestClient(app) as client:
        # Recognition timing intentionally fails for this one-second fixture;
        # waveform is independent of recognized text.
        job = wait(client,upload(client,data=buffer.getvalue()).json()['id'])
        path = f"/api/jobs/{job['id']}"
        response = client.get(path+'/waveform')
        assert response.status_code == 200
        assert response.json()['duration'] == 1
        assert len(response.json()['peaks']) <= 1200
        assert not any(response.json()['peaks'])
        assert client.get(path+'/audio').content == buffer.getvalue()
