import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from lyriclens.api import create_app
from lyriclens.config import Settings
from test_app import Decoder, Model, upload, wait
from test_translation import Translator, translate, translation_wait


@pytest.fixture
def saved(tmp_path):
    settings=Settings(root=tmp_path)
    app=create_app(settings,Decoder(),Model(),translator=Translator())
    with TestClient(app) as client:
        job=wait(client,upload(client,language='ko').json()['id'])
        path=f"/api/jobs/{job['id']}"
        segments=[dict(start=.2,end=2.8,text='Original café 世界')]
        assert client.put(path+'/edit',json=dict(pipeline='direct',segments=segments)).status_code==200
        assert translate(client,job['id']).status_code==202
        _,item=translation_wait(client,job['id'])
        assert item['state']=='completed'
        yield client,app,settings,job,path,segments


def archive_from(content, mutate):
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        entries={name:source.read(name) for name in source.namelist()}
    mutate(entries)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as target:
        for name,data in entries.items():target.writestr(name,data)
    return output.getvalue()


def restore(client,content):
    return client.post('/api/backups/restore',files={'file':('job.zip',content,'application/zip')})


def test_bilingual_export_preserves_alignment_and_rejects_stale(saved):
    client,app,settings,job,path,segments=saved
    translated='pt: '+segments[0]['text']
    assert client.get(path+'/export?translation=pt&bilingual=true').text==segments[0]['text']+'\n'+translated
    result=client.get(path+'/export?translation=pt&bilingual=true&format=srt')
    assert '00:00:00,200 --> 00:00:02,800' in result.text
    assert segments[0]['text']+'\n'+translated in result.text
    assert client.get(path+'/export?bilingual=true').status_code==422
    assert client.get(path+'/export?bilingual=true&translation=pt&format=json').status_code==422
    client.put(path+'/edit',json=dict(pipeline='direct',segments=[dict(start=.2,end=2.8,text='Changed')]))
    assert client.get(path+'/export?translation=pt&bilingual=true').status_code==409


def test_backup_roundtrip_creates_independent_snapshot(saved):
    client,app,settings,job,path,_=saved
    before=client.get(path).json()
    response=client.get(path+'/backup')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist())=={'backup.json','original','direct-raw.json'}
    restored=restore(client,response.content)
    assert restored.status_code==201,restored.text
    snapshot=restored.json()
    assert snapshot['id']!=job['id'] and snapshot['restored_from']==job['id']
    assert snapshot['results']==before['results']
    assert snapshot['translations']==before['translations']
    assert snapshot['inference']==before['inference']
    newpath=f"/api/jobs/{snapshot['id']}"
    assert client.get(newpath+'/audio').content==client.get(path+'/audio').content
    assert client.get(newpath+'/raw').json()==client.get(path+'/raw').json()
    assert client.get(newpath+'/export?translation=pt&bilingual=true').text==client.get(path+'/export?translation=pt&bilingual=true').text
    assert client.post(newpath+'/resume').status_code==409
    assert client.get(path).json()==before
    assert app.state.worker.queue.empty()


@pytest.mark.parametrize('damage',['traversal','hash','unknown-version','invalid-segments','duplicate','invalid-translation'])
def test_invalid_backups_do_not_replace_existing_jobs(saved,damage):
    client,app,settings,job,path,_=saved
    original=client.get(path+'/backup').content
    def mutate(entries):
        document=json.loads(entries['backup.json'])
        if damage=='traversal':entries['../outside.txt']=b'no'
        elif damage=='hash':entries['original']=b'changed recording'
        elif damage=='unknown-version':document['version']=99
        elif damage=='invalid-segments':document['job']['results']['direct']['edited'][0]['end']=9999
        elif damage=='invalid-translation':document['job']['translations']['direct:pt']['warning']={'invalid':'object'}
        entries['backup.json']=json.dumps(document).encode()
    damaged=archive_from(original,mutate)
    if damage=='duplicate':
        buffer=io.BytesIO(damaged)
        with pytest.warns(UserWarning), zipfile.ZipFile(buffer,'a') as archive:
            archive.writestr('original',b'duplicate')
        damaged=buffer.getvalue()
    before=app.state.store.list()
    response=restore(client,damaged)
    assert response.status_code==422,response.text
    assert app.state.store.list()==before
    assert len(list((settings.root/'jobs').iterdir()))==1
    assert not (settings.root/'outside.txt').exists()


def test_backup_active_guard_and_restore_body_limit(saved):
    client,app,settings,job,path,_=saved
    app.state.store.update(job['id'],state='processing')
    assert client.get(path+'/backup').status_code==409
    assert client.post('/api/backups/restore',content=b'',headers={'content-length':str(settings.max_bytes+3*32*1024*1024+200000)}).status_code==413
