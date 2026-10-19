import hashlib
import json
from pathlib import Path
import pytest
from lyriclens.benchmark import digest
from lyriclens.finetune import selections, plan, load_plan, labels_for, candidate_settings
from lyriclens.config import Settings


def manifest(tmp_path, **changes):
    evidence=tmp_path/'rights-fixture.txt';evidence.write_text('Synthetic unit-test evidence; not a real authorization',encoding='utf-8')
    from lyriclens.training_rights import SCOPES
    rows=[]
    for i in range(3):
        audio=tmp_path/f'{i}.wav';audio.write_bytes(f'owned test {i}'.encode())
        row=dict(id=str(i),path=audio.name,sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
                 language='en',reference='Original test phrase',reference_source='owned text',permissions='owned fixture',
                 training_allowed=True,training_permission='Owned audio/text; adaptation allowed',duration=2,conditions='synthetic fixture only',
                 language_switching=False,split='development' if i<2 else 'final',group_id=f'song-{i}')
        row.update(source_license='OWNED-CONSENT',rights_review=dict(status='verified',reviewed_by='unit-test fixture',
                   additional_terms=False,**{scope:True for scope in SCOPES},
                   evidence=[dict(path=evidence.name,sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())]))
        if i==1:row.update(changes)
        row['review']=dict(status='verified',reviewer='unit-test fixture',listened=True,text_permission_checked=True,
                           annotation_sha256=digest(row))
        rows.append(row)
    path=tmp_path/'clips.jsonl'
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    return path


def test_plan_pins_data_and_rejects_changed_manifest(tmp_path):
    source=manifest(tmp_path)
    assignment=tmp_path/'assignment.json';assignment.write_text(json.dumps(dict(train=['0'],validation=['1'])))
    output=tmp_path/'plan.json'
    result=plan(source,assignment,output,'a'*40)
    assert result['coverage']['train']['en']==1
    assert result['coverage']['train']['ja']==0
    assert load_plan(output)[1]['validation'][0]['id']=='1'
    source.write_text(source.read_text()+'\n')
    with pytest.raises(ValueError,match='manifest changed'):load_plan(output)


@pytest.mark.parametrize('changes',[
    dict(group_id='song-0'),dict(training_permission=''),dict(training_allowed=False),dict(duration=31),dict(language_switching=True),dict(split='final')])
def test_training_data_gates(tmp_path,changes):
    with pytest.raises(ValueError):selections(manifest(tmp_path,**changes),dict(train=['0'],validation=['1']))


def test_pending_review_and_final_data_are_rejected(tmp_path):
    source=manifest(tmp_path)
    with pytest.raises(ValueError,match='Final'):selections(source,dict(train=['0'],validation=['2']))
    rows=[json.loads(line) for line in source.read_text().splitlines()]
    rows[0]['review']['status']='pending'
    source.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with pytest.raises(ValueError,match='review'):selections(source,dict(train=['0'],validation=['1']))


def test_labels_do_not_truncate_and_keep_language_prefix():
    class Tokenizer:
        def set_prefix_tokens(self,**values):self.prefix=values
        def __call__(self,text,truncation):
            assert not truncation
            return type('Tokens',(),{'input_ids':[1,2,3,4]})()
    tokenizer=Tokenizer()
    assert labels_for(tokenizer,'own text','ko',1,3)==[2,3,4]
    assert tokenizer.prefix==dict(language='ko',task='transcribe',predict_timestamps=False)
    with pytest.raises(ValueError,match='token limit'):labels_for(tokenizer,'own text','ko',1,2)


def test_candidate_hash_and_local_assets(tmp_path):
    binary=tmp_path/'model.bin';binary.write_bytes(b'not an actual checkpoint; metadata test')
    marker=dict(model='lyriclens/fine-tuned-whisper-small',revision=hashlib.sha256(binary.read_bytes()).hexdigest())
    (tmp_path/'READY.json').write_text(json.dumps(marker))
    (tmp_path/'tokenizer.json').write_text('{}');(tmp_path/'preprocessor_config.json').write_text('{}')
    settings=candidate_settings(Settings(root=tmp_path/'data'),tmp_path)
    assert settings.model_dir==tmp_path and settings.revision==marker['revision']
    binary.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash changed'):candidate_settings(Settings(),tmp_path)


@pytest.mark.parametrize('device',['cpu','cuda'])
def test_tiny_random_whisper_backward_with_frozen_encoder(device):
    """Actual architecture/gradient check, not pretrained training or accuracy evidence."""
    torch=pytest.importorskip('torch')
    transformers=pytest.importorskip('transformers')
    if device=='cuda' and not torch.cuda.is_available():
        pytest.skip('CUDA-enabled training environment required')
    config=transformers.WhisperConfig(vocab_size=32,num_mel_bins=4,d_model=8,encoder_layers=1,decoder_layers=1,
        encoder_attention_heads=1,decoder_attention_heads=1,encoder_ffn_dim=16,decoder_ffn_dim=16,
        max_source_positions=8,max_target_positions=12,pad_token_id=0,bos_token_id=1,eos_token_id=2,decoder_start_token_id=1)
    model=transformers.WhisperForConditionalGeneration(config).to(device)
    model.freeze_encoder();model.config.use_cache=False;model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.train()
    optimizer=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=1e-3)
    before=model.model.decoder.embed_tokens.weight.detach().clone()
    output=model(input_features=torch.randn(1,4,16,device=device),labels=torch.tensor([[3,4,2]],device=device))
    assert torch.isfinite(output.loss)
    output.loss.backward();optimizer.step()
    assert not torch.equal(before,model.model.decoder.embed_tokens.weight)
    assert all(p.grad is None for p in model.model.encoder.parameters())


def test_training_loop_saves_checkpoint_and_validation_without_pretrained_download(tmp_path,monkeypatch):
    torch=pytest.importorskip('torch');transformers=pytest.importorskip('transformers');np=pytest.importorskip('numpy')
    source=manifest(tmp_path)
    assignment=tmp_path/'assignment.json';assignment.write_text(json.dumps(dict(train=['0'],validation=['1'])))
    frozen=tmp_path/'plan.json';plan(source,assignment,frozen,'a'*40,epochs=1)
    base=tmp_path/'base';base.mkdir();(base/'TRAINING_BASE.json').write_text(json.dumps(dict(model='openai/whisper-small',revision='a'*40)))
    config=transformers.WhisperConfig(vocab_size=32,num_mel_bins=4,d_model=8,encoder_layers=1,decoder_layers=1,
        encoder_attention_heads=1,decoder_attention_heads=1,encoder_ffn_dim=16,decoder_ffn_dim=16,
        max_source_positions=8,max_target_positions=12,pad_token_id=0,bos_token_id=1,eos_token_id=2,decoder_start_token_id=1,
        suppress_tokens=None,begin_suppress_tokens=None)
    model=transformers.WhisperForConditionalGeneration(config)
    model.generation_config.lang_to_id={'<|en|>':3};model.generation_config.task_to_id={'transcribe':4}
    model.generation_config.no_timestamps_token_id=5
    class Tokenizer:
        def set_prefix_tokens(self,**kwargs):pass
        def __call__(self,text,truncation):return type('Tokens',(),{'input_ids':[1,3,4,5,6,2]})()
    class Processor:
        tokenizer=Tokenizer()
        def feature_extractor(self,*args,**kwargs):return type('Features',(),{'input_features':np.zeros((1,4,16),dtype=np.float32)})()
        def batch_decode(self,*args,**kwargs):return ['Original test phrase']
        def save_pretrained(self,path):(Path(path)/'processor-fixture.json').write_text('{}')
    class Decoder:
        def __init__(self,settings):pass
        def decode(self,source,target):
            import wave
            with wave.open(str(target),'wb') as audio:
                audio.setparams((1,2,16000,0,'NONE','not compressed'));audio.writeframes(bytes(64000))
            return {'duration':2}
    monkeypatch.setattr(transformers.WhisperForConditionalGeneration,'from_pretrained',lambda *a,**k:model)
    monkeypatch.setattr(transformers.WhisperProcessor,'from_pretrained',lambda *a,**k:Processor())
    import lyriclens.adapters as adapters
    monkeypatch.setattr(adapters,'FFmpegDecoder',Decoder)
    from lyriclens.finetune import train
    output=tmp_path/'run';train(frozen,base,output,device='cpu')
    assert (output/'epoch-1/model.safetensors').exists()
    assert json.loads((output/'COMPLETE.json').read_text())['approved_for_app'] is False
    history=json.loads((output/'history.json').read_text())
    assert history[0]['validation'][0]['id']=='1'
    assert history[0]['mean_training_loss']>0
