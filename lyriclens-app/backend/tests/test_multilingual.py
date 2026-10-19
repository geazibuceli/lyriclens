import pytest
from fastapi.testclient import TestClient
from lyriclens.api import create_app
from lyriclens.config import Settings
from test_app import Decoder, Model, upload, wait
from test_translation import Translator, translate, translation_wait


class PassageDecoder(Decoder):
    def decode(self, source, target):
        info = super().decode(source, target)
        return {**info, 'duration': 6.0}

    def crop(self, source, target, start, end):
        target.write_bytes(b'passage')
        return end-start


@pytest.mark.parametrize('pair', [('en','ja'),('ko','zh'),('es','pt'),('fr','en')])
def test_multilingual_recognition_preserves_original_and_maps_timing(tmp_path, pair):
    model = Model()
    app = create_app(Settings(root=tmp_path), PassageDecoder(), model)
    with TestClient(app) as client:
        parent = wait(client, upload(client).json()['id'])
        path = f"/api/jobs/{parent['id']}"
        assert client.post(path+'/retranscribe-multilingual',json={}).status_code == 422
        passages = [dict(start=0,end=3,text='First passage',language=pair[0]),
                    dict(start=3,end=6,text='Second passage',language=pair[1])]
        saved = client.put(path+'/edit',json=dict(pipeline='direct',segments=passages))
        assert saved.status_code == 200
        assert saved.json()['results']['direct']['edited'][0]['language_source'] == 'user instruction'
        response = client.post(path+'/retranscribe-multilingual',json={})
        assert response.status_code == 202
        child = wait(client,response.json()['id'])
        assert child['state'] == 'completed'
        assert child['source_job_id'] == parent['id']
        assert child['sha256'] == parent['sha256']
        assert child['revision'] == parent['revision']
        assert model.languages[-2:] == list(pair)
        segments = child['results']['direct']['original']
        assert [(s['start'],s['end'],s['language']) for s in segments] == [(0.2,2.8,pair[0]),(3.2,5.8,pair[1])]
        assert client.get(path).json()['results']['direct']['original'] == parent['results']['direct']['original']
        raw = client.get(f"/api/jobs/{child['id']}/raw").json()
        assert len(raw['passages']) == 2
        passages[1]['start'] = 2.9
        assert client.put(path+'/edit',json=dict(pipeline='direct',segments=passages)).status_code == 200
        assert client.post(path+'/retranscribe-multilingual',json={}).status_code == 422
        passages[1]['language'] = 'invalid'
        assert client.put(path+'/edit',json=dict(pipeline='direct',segments=passages)).status_code == 422


def test_mixed_translation_resolves_each_segment_and_marks_language_edits_stale(tmp_path):
    translator = Translator()
    app = create_app(Settings(root=tmp_path),Decoder(),Model(),translator=translator)
    with TestClient(app) as client:
        parent = wait(client,upload(client).json()['id'])
        path = f"/api/jobs/{parent['id']}"
        passages = [dict(start=0,end=1,text='Hello',language='en'),
                    dict(start=1,end=2,text='Bonjour',language='fr'),
                    dict(start=2,end=3,text='Hola')]
        assert client.put(path+'/edit',json=dict(pipeline='direct',segments=passages)).status_code == 200
        assert translate(client,parent['id'],source='es',target='en').status_code == 202
        _,item = translation_wait(client,parent['id'],'en')
        assert item['state'] == 'completed'
        assert translator.calls == [('Bonjour','fr','en'),('Hola','es','en')]
        assert item['source_languages'] == ['en','es','fr']
        assert [s['text'] for s in item['segments']] == ['Hello','en: Bonjour','en: Hola']
        assert all(s['language']=='en' for s in item['segments'])
        passages[1]['language'] = 'pt'
        assert client.put(path+'/edit',json=dict(pipeline='direct',segments=passages)).status_code == 200
        assert client.get(path).json()['translations']['direct:en']['stale']
