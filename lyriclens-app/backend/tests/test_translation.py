import queue
import threading
import time
import pytest
from fastapi.testclient import TestClient
from lyriclens.api import create_app
from lyriclens.config import Settings, LANGUAGES
from lyriclens.translation import key, MODEL, REVISION
from test_app import Decoder, Model, upload, wait


class Translator:
    def __init__(self):
        self.calls = []

    def translate(self, text, source, target):
        self.calls.append((text,source,target))
        return f'{target}: {text}'


@pytest.fixture
def translated_app(tmp_path):
    translator = Translator()
    settings = Settings(root=tmp_path)
    app = create_app(settings,Decoder(),Model(),translator=translator)
    with TestClient(app) as client:
        job = wait(client,upload(client,language='ko').json()['id'])
        yield client,app,job,translator


def translation_wait(client, identifier, target='pt'):
    for _ in range(300):
        job = client.get(f'/api/jobs/{identifier}').json()
        item = job.get('translations',{}).get(key('direct',target),{})
        if item.get('state') not in {'queued','processing',None}:
            return job,item
        time.sleep(.01)
    pytest.fail('Translation did not finish')


def translate(client, identifier, source='ko', target='pt'):
    return client.post(f'/api/jobs/{identifier}/translate',json={
        'pipeline':'direct','source_language':source,'target_language':target})


def test_reviewed_source_translation_edit_and_separate_exports(translated_app):
    client,app,job,translator = translated_app
    path = f"/api/jobs/{job['id']}"
    original = job['results']['direct']['original']
    reviewed = [{'start':.3,'end':2.7,'text':'Reviewed café 안녕'}]
    assert client.put(path+'/edit',json={'pipeline':'direct','segments':reviewed}).status_code==200
    assert client.get('/api/translation').json()['prepared']
    assert translate(client,job['id']).status_code==202
    saved,item = translation_wait(client,job['id'])
    assert translator.calls==[(reviewed[0]['text'],'ko','pt')]
    assert item['source_segments']==reviewed and item['source_version']=='edited'
    assert item['model_id']==MODEL and item['revision']==REVISION
    assert item['segments'][0]['start']==.3 and item['segments'][0]['end']==2.7
    assert saved['results']['direct']['original']==original
    assert saved['results']['direct']['edited']==reviewed
    response = client.put(path+'/translation',json={'pipeline':'direct','target_language':'pt','texts':['Olá, tradução revisada']})
    assert response.status_code==200
    updated = response.json()['translations']['direct:pt']
    assert updated['segments']==item['segments']
    assert updated['edited'][0]['text']=='Olá, tradução revisada'
    assert client.get(path+'/export?translation=pt').text=='Olá, tradução revisada'
    assert client.get(path+'/export').text==reviewed[0]['text']
    assert '00:00:00,300 --> 00:00:02,700' in client.get(path+'/export?translation=pt&format=srt').text
    assert client.get(path+'/export?translation=pt&format=json').json()['source_segments']==reviewed
    assert client.get(path+'/export?translation=pt&original=true').text.startswith('pt: ')
    assert client.put(path+'/translation',json={'target_language':'pt','texts':[]}).status_code==422
    assert client.put(path+'/edit',json={'pipeline':'direct','segments':[dict(start=.3,end=2.7,text='Changed')]}).status_code==200
    assert client.get(path).json()['translations']['direct:pt']['stale']
    assert client.get(path+'/export?translation=pt').status_code==409
    assert client.put(path+'/translation',json={'target_language':'pt','texts':['Old source']}).status_code==409
    assert translate(client,job['id']).status_code==202
    _,fresh = translation_wait(client,job['id'])
    assert fresh['stale'] is False and fresh['source_segments'][0]['text']=='Changed'


def test_all_language_pair_routing_and_validation(translated_app):
    client,app,job,translator = translated_app
    for source in LANGUAGES:
        for target in LANGUAGES:
            response = translate(client,job['id'],source,target)
            if source==target:
                assert response.status_code==422
            else:
                assert response.status_code==202
                _,item = translation_wait(client,job['id'],target)
                assert item['state']=='completed'
                assert translator.calls[-1][1:]==(source,target)
    assert translate(client,job['id'],'de','pt').status_code==422
    assert translate(client,job['id'],'ko','xx').status_code==422
    path = f"/api/jobs/{job['id']}"
    assert client.put(path+'/edit',json={'pipeline':'direct','segments':[]}).status_code==200
    assert translate(client,job['id']).status_code==422


def test_translation_queue_full_keeps_previous_output(translated_app,monkeypatch):
    client,app,job,_ = translated_app
    assert translate(client,job['id']).status_code==202
    _,previous = translation_wait(client,job['id'])
    def full(_):
        raise queue.Full
    monkeypatch.setattr(app.state.translation_worker.queue,'put_nowait',full)
    assert translate(client,job['id']).status_code==429
    current = client.get(f"/api/jobs/{job['id']}").json()['translations']['direct:pt']
    assert current==previous


def test_cancel_translation_and_guard_active_deletion(tmp_path):
    entered,release = threading.Event(),threading.Event()
    class Slow(Translator):
        def translate(self,*args):
            entered.set()
            assert release.wait(timeout=5)
            return super().translate(*args)
    app = create_app(Settings(root=tmp_path),Decoder(),Model(),translator=Slow())
    with TestClient(app) as client:
        job = wait(client,upload(client).json()['id'])
        path = f"/api/jobs/{job['id']}"
        try:
            assert translate(client,job['id']).status_code==202
            assert entered.wait(timeout=3)
            assert client.delete(path).status_code==409
            assert translate(client,job['id']).status_code==409
            assert client.post(path+'/translation/cancel',json={'source_language':'ko','target_language':'pt'}).status_code==200
        finally:
            release.set()
        _,item = translation_wait(client,job['id'])
        assert item['state']=='canceled'
        assert client.delete(path).status_code==204


def test_missing_model_and_translation_failures_do_not_change_asr(tmp_path):
    settings = Settings(root=tmp_path)
    with TestClient(create_app(settings,Decoder(),Model())) as client:
        job = wait(client,upload(client).json()['id'])
        assert not client.get('/api/translation').json()['prepared']
        assert translate(client,job['id']).status_code==409
    class Failed(Translator):
        def translate(self,*args):
            raise ValueError('Segment too long; no text truncated')
    with TestClient(create_app(settings,Decoder(),Model(),translator=Failed())) as client:
        assert translate(client,job['id']).status_code==202
        saved,item = translation_wait(client,job['id'])
        assert item['state']=='failed' and 'no text truncated' in item['error']
        assert saved['state']=='completed' and saved['results']==job['results']


def test_translation_restart_recovery(translated_app):
    client,app,job,_ = translated_app
    assert translate(client,job['id']).status_code==202
    translation_wait(client,job['id'])
    with app.state.store.lock:
        saved = app.state.store.get(job['id'])
        saved['translations']['direct:pt']['state']='processing'
        app.state.store.put(saved)
    from lyriclens.translation import TranslationWorker
    worker = TranslationWorker(app.state.worker.settings,app.state.store,Translator())
    try:
        worker.start()
        recovered = app.state.store.get(job['id'])['translations']['direct:pt']
        assert recovered['state']=='interrupted'
    finally:
        worker.stop()
