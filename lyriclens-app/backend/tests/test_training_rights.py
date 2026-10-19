import hashlib
import json
from pathlib import Path
import pytest
from lyriclens.training_rights import validate_rights,pending_rights,SCOPES,prepare_original


def record(tmp_path):
    evidence=tmp_path/'permission.txt'
    evidence.write_text('Synthetic test evidence only',encoding='utf-8')
    return dict(source_license='OWNED-CONSENT',rights_review=dict(status='verified',reviewed_by='test fixture',
                additional_terms=False,**{scope:True for scope in SCOPES},
                evidence=[dict(path=evidence.name,sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())]))


@pytest.mark.parametrize('license',['CC-BY-NC-SA-4.0','CC-BY-ND-4.0','unknown','MIT'])
def test_restrictive_or_unreviewed_sources_are_not_admitted(tmp_path,license):
    row=record(tmp_path);row['source_license']=license
    with pytest.raises(ValueError,match='policy'):validate_rights(row,tmp_path/'manifest.jsonl')


def test_rights_require_scopes_and_current_evidence(tmp_path):
    row=record(tmp_path);validate_rights(row,tmp_path/'manifest.jsonl')
    row['rights_review']['composition']=False
    with pytest.raises(ValueError,match='separately'):validate_rights(row,tmp_path/'manifest.jsonl')
    row['rights_review']['composition']=True
    (tmp_path/'permission.txt').write_text('Changed evidence')
    with pytest.raises(ValueError,match='changed'):validate_rights(row,tmp_path/'manifest.jsonl')


def test_pending_and_additional_agreements_are_rejected(tmp_path):
    row=record(tmp_path);row['rights_review']['additional_terms']=True
    with pytest.raises(ValueError,match='additional'):validate_rights(row,tmp_path/'manifest.jsonl')
    row['rights_review']=pending_rights()
    with pytest.raises(ValueError):validate_rights(row,tmp_path/'manifest.jsonl')


def test_evidence_cannot_escape_manifest_directory(tmp_path):
    row=record(tmp_path);row['rights_review']['evidence'][0]['path']='../outside.txt'
    with pytest.raises(ValueError,match='within'):validate_rights(row,tmp_path/'manifest.jsonl')


def test_original_recording_preparation_is_pending_and_non_destructive(tmp_path,monkeypatch):
    import lyriclens.adapters as adapters
    class Decoder:
        def __init__(self,settings):pass
        def decode(self,source,target):return {'duration':3}
    monkeypatch.setattr(adapters,'FFmpegDecoder',Decoder)
    audio=tmp_path/'original.wav';audio.write_bytes(b'owned fixture')
    reference=tmp_path/'text.txt';reference.write_text('Original test text',encoding='utf-8')
    output=tmp_path/'review.json'
    row=prepare_original(audio,reference,output,'own-1','en','own-session-1')
    assert row['review']['status']=='pending' and not row['training_allowed']
    assert row['rights_review']==pending_rights()
    assert audio.read_bytes()==b'owned fixture'
    assert json.loads(output.read_text())['clips'][0]['reference']=='Original test text'
    with pytest.raises(ValueError,match='exists'):prepare_original(audio,reference,output,'own-1','en','session')
