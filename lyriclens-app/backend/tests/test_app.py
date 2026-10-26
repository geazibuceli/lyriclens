import hashlib
import json
import subprocess
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from lyriclens.api import create_app
from lyriclens.config import Settings, LANGUAGES
from lyriclens.domain import validate_segments, srt
from lyriclens.store import Store
from lyriclens.adapters import FFmpegDecoder
from lyriclens.evaluate import normalize, metrics, load_manifest


class Decoder:
    def decode(self, source, target):
        if source.read_bytes() == b"corrupt":
            raise ValueError("Audio could not be decoded")
        target.write_bytes(b"decoded")
        return {"duration": 3.0, "timeline": "identity"}


class Model:
    def __init__(self):
        self.languages = []

    def transcribe(self, audio, language):
        self.languages.append(language)
        return {"segments":[{"start":0.2,"end":2.8,"text":"안녕 日本語 中文 café olá"}], "language": language or "ko", "language_source":"user instruction" if language else "whole-clip model estimate"}


@pytest.fixture
def setup(tmp_path):
    settings = Settings(root=tmp_path)
    model = Model()
    app = create_app(settings, Decoder(), model)
    with TestClient(app) as client:
        yield client, settings, app, model


def upload(client, data=b"audio", **params):
    return client.post("/api/jobs", files={"file":("song.wav",data,"audio/wav")}, data=params)


def wait(client, job_id):
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] not in {"queued", "processing"}:
            return job
        time.sleep(.01)
    pytest.fail("Worker did not finish")


@pytest.mark.parametrize("language", list(LANGUAGES)+["auto"])
def test_vertical_slice_and_unicode(setup, language):
    client, settings, app, model = setup
    response = upload(client, language=language)
    assert response.status_code == 202
    job = wait(client, response.json()["id"])
    assert job["state"] == "completed"
    assert model.languages == [None if language == "auto" else language]
    assert job["sha256"] == hashlib.sha256(b"audio").hexdigest()
    original = job["results"]["direct"]["original"]
    edited = [{"start":.3,"end":2.5,"text":"Olá 世界"}]
    path = f"/api/jobs/{job['id']}"
    assert client.put(path+"/edit", json={"pipeline":"direct","segments":edited}).status_code == 200
    saved = client.get(path).json()
    assert saved["results"]["direct"]["original"] == original
    assert saved["results"]["direct"]["edited"] == edited
    assert client.get(path+"/export").text == "Olá 世界"
    assert "안녕" in client.get(path+"/export?original=true").text
    assert "00:00:00,300 --> 00:00:02,500" in client.get(path+"/export?format=srt").text
    lyrics = client.get(path+"/export?format=lrc")
    assert lyrics.status_code == 200
    assert lyrics.text == "[00:00.30]" + edited[0]['text'] + "\n"
    assert lyrics.headers['content-disposition'].endswith('.lrc"')
    assert client.get(path+"/export?format=json").json()["sha256"] == job["sha256"]
    assert client.get(path+"/raw").json()["segments"] == original
    assert client.get(path+"/audio").content == b"audio"
    assert client.put(path+"/edit", json={"pipeline":"direct","segments":[{"start":0,"end":10,"text":"x"}]}).status_code == 422
    assert client.delete(path).status_code == 204
    assert not (settings.root/"jobs"/job["id"]).exists()
    assert client.get(path).status_code == 404


def test_rename_preserves_original_and_persists_in_library(setup):
    client, settings, app, model = setup
    job = wait(client, upload(client).json()['id'])
    path = f"/api/jobs/{job['id']}"
    response = client.patch(path, json={'title': '  Ensaio café 世界  '})
    assert response.status_code == 200
    assert response.json()['title'] == 'Ensaio café 世界'
    assert response.json()['filename'] == job['filename']
    assert response.json()['sha256'] == job['sha256']
    assert client.get('/api/jobs').json()[0]['title'] == 'Ensaio café 世界'
    assert client.patch(path, json={'title': 'x' * 201}).status_code == 422
    assert client.get(path).json()['title'] == 'Ensaio café 世界'
    assert client.patch(path, json={'title': '   '}).json()['title'] == ''
    assert client.patch('/api/jobs/missing', json={'title': 'test'}).status_code == 404


def test_delete_retries_busy_audio_and_preserves_record_on_failure(setup, monkeypatch):
    import shutil
    client, settings, app, _ = setup
    job = wait(client, upload(client).json()['id'])
    path = f"/api/jobs/{job['id']}"
    original_rmtree = shutil.rmtree
    attempts = []
    def locked(folder):
        attempts.append(folder)
        raise PermissionError('File in use')
    with monkeypatch.context() as patch:
        patch.setattr(shutil, 'rmtree', locked)
        patch.setattr('lyriclens.routes.jobs.time.sleep', lambda _: None)
        response = client.delete(path)
        assert response.status_code == 409
        assert 'still in use' in response.json()['detail']
        assert len(attempts) == 5
        assert client.get(path).status_code == 200
    attempts.clear()
    def temporarily_locked(folder):
        attempts.append(folder)
        if len(attempts) == 1:
            raise PermissionError('File in use')
        original_rmtree(folder)
    with monkeypatch.context() as patch:
        patch.setattr(shutil, 'rmtree', temporarily_locked)
        patch.setattr('lyriclens.routes.jobs.time.sleep', lambda _: None)
        assert client.delete(path).status_code == 204
    assert len(attempts) == 2
    assert client.get(path).status_code == 404
    assert not (settings.root/'jobs'/job['id']).exists()


def test_delete_recovers_missing_audio_folder(setup):
    import shutil
    client, settings, _, _ = setup
    job = wait(client, upload(client).json()['id'])
    folder = (settings.root/'jobs'/job['id']).resolve()
    assert folder.parent == (settings.root/'jobs').resolve()
    shutil.rmtree(folder)
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_validation_and_failure_cleanup(setup):
    client, settings, *_ = setup
    settings.max_bytes = 5
    assert upload(client,b"too large").status_code == 413
    assert upload(client,b"").status_code == 422
    assert upload(client,language="xx").status_code == 422
    assert client.post("/api/jobs",files={"file":("bad.exe",b"a")}).status_code == 415
    settings.max_bytes = 100
    response = upload(client,b"corrupt")
    job = wait(client,response.json()["id"])
    assert job["state"] == "failed"
    folder = settings.root/"jobs"/job["id"]
    assert (folder/"original").exists()
    assert not (folder/"decoded.wav").exists()


def test_optional_separation_failure_preserves_direct(setup):
    client,*_ = setup
    job = wait(client,upload(client,pipeline="both").json()["id"])
    assert job["state"] == "completed"
    assert job["results"]["direct"]["state"] == "completed"
    assert job["results"]["vocals"]["state"] == "failed"


def test_queue_full_cleans_rejected_upload(tmp_path):
    # Without lifespan the worker does not consume, making queue pressure deterministic.
    app = create_app(Settings(root=tmp_path, queue_size=1), Decoder(), Model())
    client = TestClient(app)
    assert upload(client).status_code == 202
    assert upload(client).status_code == 429
    assert len(app.state.store.list()) == 1
    assert len(list((tmp_path/'jobs').iterdir())) == 1


def test_empty_output_is_not_filled(tmp_path):
    class Empty(Model):
        def transcribe(self,*args):
            return {'segments':[], 'language':'en'}
    app = create_app(Settings(root=tmp_path), Decoder(), Empty())
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        result = job['results']['direct']
        assert result['original'] == []
        assert result['original_text'] == ''
        assert any('No words returned' in w for w in result['warnings'])


def test_restart_recovery(tmp_path):
    store = Store(tmp_path)
    for state in ("queued","processing","completed"):
        store.put({"id":state,"state":state,"created_at":"now"})
    store.recover()
    assert store.get("queued")["state"] == "interrupted"
    assert store.get("processing")["state"] == "interrupted"
    assert store.get("completed")["state"] == "completed"


def test_cooperative_cancel_and_active_delete(tmp_path):
    import threading
    entered, release = threading.Event(), threading.Event()
    class Slow(Model):
        def transcribe(self, *args):
            entered.set()
            release.wait(5)
            return super().transcribe(*args)
    app = create_app(Settings(root=tmp_path),Decoder(),Slow())
    with TestClient(app) as client:
        job_id = upload(client).json()["id"]
        assert entered.wait(2)
        path = f"/api/jobs/{job_id}"
        try:
            assert client.delete(path).status_code == 409
            assert client.post(path+"/cancel").json()["cancel_requested"]
            assert client.get(path).json()["state"] == "processing"
        finally:
            release.set()
        assert wait(client,job_id)["state"] == "canceled"
        assert client.delete(path).status_code == 204


@pytest.mark.parametrize("segments", [[{"start":-1,"end":1,"text":"a"}],[{"start":2,"end":1,"text":"a"}],[{"start":0,"end":4,"text":"a"}],[{"start":0,"end":float('nan'),"text":"a"}]])
def test_timestamp_rejection(segments):
    with pytest.raises(ValueError):
        validate_segments(segments,3)


def test_metrics():
    assert normalize("CAFÉ! Olá") == "café olá"
    assert normalize("e\u0301") == "é"
    assert metrics("日本語", "日本", "ja")["cer"] == pytest.approx(1/3)
    assert metrics("你好", "你好", "zh")["wer"] is None
    assert metrics("", "invented", "en")["cer"] is None
    assert metrics("", "", "en")["cer"] == 0
    assert metrics("la la", "la", "en")["wer"] == .5
    assert metrics("avó", "avo", "pt")["cer"] > 0


def test_ffmpeg_failures(tmp_path,monkeypatch):
    settings = Settings(root=tmp_path)
    def fail(*args,**kwargs):
        assert isinstance(args[0],list)
        raise subprocess.CalledProcessError(1,args[0])
    monkeypatch.setattr(subprocess,"run",fail)
    with pytest.raises(ValueError,match="could not be decoded"):
        FFmpegDecoder(settings).decode(tmp_path/"untrusted",tmp_path/"derived.wav")
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired(args[0],1)
    monkeypatch.setattr(subprocess,"run",timeout)
    with pytest.raises(ValueError,match="time limit"):
        FFmpegDecoder(settings).decode(tmp_path/"untrusted",tmp_path/"derived.wav")


@pytest.mark.parametrize("duration",[0,601])
def test_decoded_duration_limit(tmp_path,monkeypatch,duration):
    import wave
    def decode(command,**kwargs):
        with wave.open(command[-1],"wb") as wav:
            wav.setparams((1,2,16000,0,"NONE","not compressed"))
            wav.writeframes(b"\0\0"*(16000*duration))
    monkeypatch.setattr(subprocess,"run",decode)
    with pytest.raises(ValueError,match="Audio must be"):
        FFmpegDecoder(Settings(root=tmp_path)).decode(tmp_path/"audio",tmp_path/"out.wav")


def test_health_never_initializes_model(setup):
    client,settings,app,model = setup
    assert client.get('/api/health').json()['status'] == 'ok'
    assert not client.get('/api/models').json()['prepared']
    assert model.languages == []
    assert 'Job' in client.get('/openapi.json').json()['components']['schemas']


def test_body_limit_before_multipart_spool(setup):
    client,settings,*_ = setup
    response = client.post('/api/jobs',content=b'x'*(settings.max_bytes+65537),headers={'Content-Type':'multipart/form-data; boundary=test'})
    assert response.status_code == 413


def test_both_success(tmp_path):
    class Separator:
        def separate(self,audio,directory):
            return audio
    app = create_app(Settings(root=tmp_path),Decoder(),Model(),Separator())
    with TestClient(app) as client:
        job = wait(client,upload(client,pipeline='both').json()['id'])
        assert all(r['state']=='completed' for r in job['results'].values())
        assert job['results']['vocals']['provenance']['separator']


def test_invalid_model_timing_preserves_raw(tmp_path):
    class Invalid(Model):
        def transcribe(self,*args):
            raw = super().transcribe(*args)
            raw['segments'][0]['end'] = 30
            return raw
    app = create_app(Settings(root=tmp_path),Decoder(),Invalid())
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        assert job['state']=='failed'
        assert client.get(f"/api/jobs/{job['id']}/raw").json()['segments'][0]['end']==30


@pytest.mark.parametrize('pipeline', ['direct', 'vocals'])
def test_unordered_model_segments_preserve_times_and_raw(tmp_path, pipeline):
    emitted = [
        {'start': 1.5, 'end': 2.8, 'text': 'later'},
        {'start': 0.5, 'end': 2.0, 'text': 'earlier overlapping'},
        {'start': 0.5, 'end': 1.0, 'text': 'same start'},
    ]

    class Unordered(Model):
        def transcribe(self, *args):
            return {**super().transcribe(*args), 'segments': emitted}

    class Separator:
        def separate(self, audio, directory):
            return audio

    app = create_app(Settings(root=tmp_path), Decoder(), Unordered(), Separator())
    with TestClient(app) as client:
        job = wait(client, upload(client, pipeline=pipeline).json()['id'])
        assert job['state'] == 'completed'
        result = job['results'][pipeline]
        assert result['original'] == [emitted[1], emitted[2], emitted[0]]
        assert any('reordered' in warning for warning in result['warnings'])
        path = f"/api/jobs/{job['id']}"
        assert client.get(path + f'/raw?pipeline={pipeline}').json()['segments'] == emitted
        # User edits remain strict: normalization only applies to model output.
        assert client.put(path + '/edit', json={'pipeline': pipeline, 'segments': emitted}).status_code == 422


def test_manifest_integrity(tmp_path):
    audio = tmp_path/'clip.wav'
    audio.write_bytes(b'licensed-recording')
    manifest = tmp_path/'clips.jsonl'
    row = {'id':'clip','path':'clip.wav','sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'language':'pt','reference':'Olá','reference_source':'Original author','permissions':'Original recording and reference, CC0','duration':1,'conditions':'studio','language_switching':False,'split':'development'}
    manifest.write_text(json.dumps(row),encoding='utf-8')
    assert load_manifest(manifest)[0]['reference']=='Olá'
    audio.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        load_manifest(manifest)


def test_manual_region_context_and_original_timestamp_mapping(tmp_path):
    class RegionDecoder(Decoder):
        def decode(self,source,target):
            super().decode(source,target)
            return {"duration":10.0,"timeline":"identity"}
        def crop(self,source,target,start,end):
            target.write_bytes(b"cropped")
            return end-start
    model = Model()
    app = create_app(Settings(root=tmp_path),RegionDecoder(),model)
    with TestClient(app) as client:
        parent = wait(client,upload(client,language='en').json()['id'])
        path = f"/api/jobs/{parent['id']}/retranscribe"
        assert client.post(path,json={'language':'auto','start':5,'end':6}).status_code==422
        assert client.post(path,json={'language':'ja','start':5,'end':11}).status_code==422
        response = client.post(path,json={'language':'ja','start':5,'end':6,'context_seconds':2})
        assert response.status_code==202
        child = wait(client,response.json()['id'])
        assert child['state']=='completed'
        assert child['region']['start']==3
        assert child['region']['end']==8
        assert child['results']['direct']['original'][0]['start']==pytest.approx(3.2)
        assert child['results']['direct']['original'][0]['end']==pytest.approx(5.8)
        assert child['source_job_id']==parent['id']
        assert model.languages==['en','ja']
        assert client.delete(f"/api/jobs/{parent['id']}").status_code==204
        assert client.get(f"/api/jobs/{child['id']}/audio").content==b'audio'


@pytest.mark.parametrize('extension',['wav','mp3','flac','m4a','mp4'])
def test_real_ffmpeg_formats_without_model(tmp_path,extension):
    import shutil
    settings = Settings(root=tmp_path)
    if not shutil.which(settings.ffmpeg):
        pytest.skip('FFmpeg not installed; install the tools dependency group')
    source = tmp_path/f'tone.{extension}'
    subprocess.run([settings.ffmpeg,'-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=220:duration=1.2',str(source)],check=True,timeout=20)
    info = FFmpegDecoder(settings).decode(source,tmp_path/'decoded.wav')
    assert info['duration']==pytest.approx(1.2,abs=.05)


@pytest.mark.parametrize('has_audio', [True, False])
def test_mp4_video_upload_extracts_audio_or_reports_missing_track(tmp_path, has_audio):
    import shutil
    settings = Settings(root=tmp_path/'data')
    if not shutil.which(settings.ffmpeg):
        pytest.skip('FFmpeg unavailable')
    source = tmp_path/'video.MP4'
    command = [settings.ffmpeg,'-nostdin','-v','error','-y','-f','lavfi','-i','color=c=blue:s=64x64:r=10:d=3.2']
    if has_audio:
        command += ['-f','lavfi','-i','sine=frequency=220:duration=3.2','-c:a','aac','-shortest']
    command += ['-c:v','libx264','-pix_fmt','yuv420p',str(source)]
    subprocess.run(command,check=True,capture_output=True,timeout=20)
    with TestClient(create_app(settings, FFmpegDecoder(settings), Model())) as client:
        response = client.post('/api/jobs',files={'file':(source.name,source.read_bytes(),'video/mp4')},data={'language':'en'})
        assert response.status_code == 202
        job = wait(client,response.json()['id'])
        assert client.get(f"/api/jobs/{job['id']}/audio").content == source.read_bytes()
        if has_audio:
            assert job['state'] == 'completed'
            assert job['audio']['duration'] == pytest.approx(3.2,abs=.05)
            assert job['audio']['sample_rate'] == 16000
            assert job['audio']['channels'] == 1
        else:
            assert job['state'] == 'failed'
            assert 'audio track' in job['error']


def test_exact_digital_silence_bypasses_models(tmp_path):
    import wave
    from lyriclens.adapters import WhisperTranscriber,DemucsSeparator,digital_silence
    audio=tmp_path/'silence.wav'
    with wave.open(str(audio),'wb') as wav:
        wav.setparams((1,2,16000,0,'NONE','not compressed'))
        wav.writeframes(b'\x00\x00'*16000)
    assert digital_silence(audio)
    settings=Settings(root=tmp_path)
    raw=WhisperTranscriber(settings).transcribe(audio,None)
    assert raw['segments']==[]
    assert raw['model_executed'] is False
    assert raw['language'] is None
    assert DemucsSeparator(settings).separate(audio,tmp_path/'stems')==audio


def test_native_model_error_does_not_expose_local_paths(tmp_path,monkeypatch):
    from lyriclens.adapters import WhisperTranscriber
    settings=Settings(root=tmp_path)
    settings.model_dir.mkdir(parents=True)
    (settings.model_dir/'READY.json').write_text('{}',encoding='utf-8')
    adapter=WhisperTranscriber(settings)
    def fail(*args):
        raise ValueError('Cannot open C:/private/cache/model.bin')
    monkeypatch.setattr(adapter,'_infer',fail)
    with pytest.raises(ValueError) as error:
        adapter.transcribe(tmp_path/'missing.wav','en')
    assert 'private' not in str(error.value)
    assert 'model.bin' not in str(error.value)
    assert 'local server log' in str(error.value)


def test_explicit_model_selection_and_region_inheritance(setup):
    client,settings,app,model=setup
    from lyriclens.profiles import LARGE_MODEL,LARGE_REVISION
    profiles=client.get('/api/models').json()['profiles']
    assert {p['id'] for p in profiles}=={'configured','aligned','large-v3'}
    assert upload(client,model_profile='unknown').status_code==422
    job=wait(client,upload(client,model_profile='large-v3',language='ko').json()['id'])
    assert job['model_id']==LARGE_MODEL
    assert job['revision']==LARGE_REVISION
    assert job['inference']['word_timestamps'] is True
    assert job['results']['direct']['provenance']['model_id']==LARGE_MODEL
    child=client.post(f"/api/jobs/{job['id']}/retranscribe",json={'language':'ja','start':0,'end':3,'context_seconds':0}).json()
    assert child['model_id']==LARGE_MODEL
    assert child['revision']==LARGE_REVISION
    assert child['inference']==job['inference']


@pytest.mark.parametrize('profile', ['aligned', 'large-v3'])
def test_region_retry_can_upgrade_model_without_changing_source(setup, profile):
    from lyriclens.profiles import profile_settings
    client, settings, app, model = setup
    parent = wait(client, upload(client, language='en').json()['id'])
    before = client.get(f"/api/jobs/{parent['id']}").json()
    selected = profile_settings(settings, profile)
    selected.model_dir.mkdir(parents=True, exist_ok=True)
    (selected.model_dir / 'READY.json').write_text('{}')
    response = client.post(f"/api/jobs/{parent['id']}/retranscribe",
                           json={'language': 'en', 'start': 0, 'end': 3,
                                 'context_seconds': 0, 'model_profile': profile})
    assert response.status_code == 202
    child = wait(client, response.json()['id'])
    assert child['model_profile'] == profile
    assert child['model_id'] == selected.model_id
    assert child['inference']['word_timestamps'] is True
    assert child['source_job_id'] == parent['id']
    assert client.get(f"/api/jobs/{parent['id']}").json() == before


def test_region_retry_rejects_unknown_or_unprepared_override(setup):
    client, settings, app, model = setup
    parent = wait(client, upload(client, language='en').json()['id'])
    count = len(client.get('/api/jobs').json())
    path = f"/api/jobs/{parent['id']}/retranscribe"
    body = {'language': 'en', 'start': 0, 'end': 3, 'model_profile': 'large-v3'}
    assert client.post(path, json=body).status_code == 409
    assert client.post(path, json={**body, 'model_profile': 'unknown'}).status_code == 422
    assert len(client.get('/api/jobs').json()) == count


def test_gap_protection_is_opt_in_and_can_be_disabled_on_region_retry(setup):
    client, settings, app, model = setup
    ordinary = wait(client, upload(client, language='en').json()['id'])
    assert 'hallucination_silence_threshold' not in ordinary['inference']
    protected = wait(client, upload(client, language='en', reduce_hallucinations='true').json()['id'])
    assert protected['inference']['hallucination_silence_threshold'] == 2.0
    assert protected['inference']['word_timestamps'] is True
    assert protected['inference']['vad_filter'] is True
    assert protected['inference']['vad_parameters'] == {'threshold': .1, 'min_silence_duration_ms': 10000, 'speech_pad_ms': 3000}
    assert any('skip legitimate' in warning for warning in protected['results']['direct']['warnings'])
    path = f"/api/jobs/{protected['id']}/retranscribe"
    body = {'language': 'en', 'start': 0, 'end': 3, 'context_seconds': 0}
    inherited = client.post(path, json=body)
    assert inherited.status_code == 202
    assert inherited.json()['inference']['hallucination_silence_threshold'] == 2.0
    disabled = client.post(path, json={**body, 'reduce_hallucinations': False})
    assert disabled.status_code == 202
    assert 'hallucination_silence_threshold' not in disabled.json()['inference']
    assert disabled.json()['inference']['vad_filter'] is False
    assert 'vad_parameters' not in disabled.json()['inference']
    # Verify production cache separation in addition to the injected API adapter.
    from lyriclens.worker import Worker
    from lyriclens.store import Store
    production = Worker(settings, Store(settings.root))
    assert production.transcriber_for(ordinary) is not production.transcriber_for(protected)
    assert production.transcriber_for(protected).settings.hallucination_silence_threshold == 2.0
    assert production.transcriber_for(protected).settings.vad_filter is True


def test_aligned_profile_reuses_weights_and_region_keeps_alignment(setup):
    from lyriclens.profiles import profile_settings
    client, settings, app, model = setup
    aligned = profile_settings(settings, 'aligned')
    assert aligned.model_dir == settings.model_dir
    assert aligned.model_id == settings.model_id and aligned.revision == settings.revision
    assert aligned.word_timestamps and not settings.word_timestamps
    job = wait(client, upload(client, model_profile='aligned', language='pt').json()['id'])
    assert job['model_profile'] == 'aligned'
    assert job['model_id'] == settings.model_id
    assert job['inference']['word_timestamps'] is True
    child = client.post(f"/api/jobs/{job['id']}/retranscribe",
                        json={'language': 'pt', 'start': 0, 'end': 3, 'context_seconds': 0})
    assert child.status_code == 202
    assert child.json()['model_profile'] == 'aligned'
    assert child.json()['inference']['word_timestamps'] is True


def test_worker_selects_requested_model_and_reuses_bounded_cache(tmp_path):
    from lyriclens.worker import Worker
    settings=Settings(root=tmp_path)
    worker=Worker(settings,Store(tmp_path))
    def job(identifier):
        return {'model_id':identifier,'revision':'fixed','inference':{'device':'cpu','compute_type':'int8'}}
    small=worker.transcriber_for(job('small'))
    assert small is worker.transcriber_for(job('small'))
    large=worker.transcriber_for(job('large'))
    assert large.settings.model_id=='large'
    assert small is not large
    worker.transcriber_for(job('third'))
    assert len(worker.transcribers)==2
    assert worker.transcriber_for(job('large')) is large
    aligned=job('large')
    aligned['inference']['word_timestamps']=True
    assert worker.transcriber_for(aligned).settings.word_timestamps is True
    assert worker.transcriber_for(aligned) is not large


def test_real_model_smoke(tmp_path):
    import os
    if not os.getenv("LYRICLENS_SMOKE_AUDIO"):
        pytest.skip("Opt-in only: set LYRICLENS_SMOKE_AUDIO to an authorized audio path; pre-download model")
    from lyriclens.adapters import WhisperTranscriber
    settings = Settings()
    info = FFmpegDecoder(settings).decode(Path(os.environ["LYRICLENS_SMOKE_AUDIO"]),tmp_path/"decoded.wav")
    raw = WhisperTranscriber(settings).transcribe(tmp_path/"decoded.wav",os.getenv("LYRICLENS_SMOKE_LANGUAGE"))
    validate_segments(raw["segments"],info["duration"])


def test_real_separation_model_is_reused(tmp_path):
    import os
    if not os.getenv("LYRICLENS_SMOKE_AUDIO"):
        pytest.skip("Opt-in only: requires an authorized clip and prepared separation model")
    from lyriclens.adapters import DemucsSeparator
    settings=Settings()
    separator=DemucsSeparator(settings)
    if not (settings.root/'separation-models'/'955717e8-8726e21a.th').exists():
        pytest.skip("Optional separation model not prepared")
    decoded=tmp_path/'decoded.wav'
    FFmpegDecoder(settings).decode(Path(os.environ['LYRICLENS_SMOKE_AUDIO']),decoded)
    try:
        assert separator.separate(decoded,tmp_path/'first').exists()
        process_id=separator.process.pid
        assert separator.separate(decoded,tmp_path/'second').exists()
        assert separator.process.pid==process_id
    finally:
        separator.close()
