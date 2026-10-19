"""Offline, reviewed-data Whisper Small decoder fine-tuning. No automatic promotion."""
import argparse
import hashlib
import json
import math
import random
import re
import tempfile
from pathlib import Path
from .benchmark import digest
from .config import Settings, LANGUAGES
from .evaluate import load_manifest, metrics
from .training_rights import validate_rights

BASE_MODEL='openai/whisper-small'


def write_new(path, value):
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2)


def selections(manifest, assignment):
    rows=load_manifest(manifest,require_reviewed=True)
    by_id={row['id']:row for row in rows}
    selected={}
    groups, hashes=set(),set()
    for split in ('train','validation'):
        identifiers=assignment.get(split)
        if not isinstance(identifiers,list) or not identifiers or len(set(identifiers))!=len(identifiers):
            raise ValueError('Provide nonempty, unique train and validation clip ID lists')
        selected[split]=[]
        current_groups,current_hashes=set(),set()
        for identifier in identifiers:
            if identifier not in by_id:
                raise ValueError('Unknown training/validation clip ID')
            row=by_id[identifier]
            if row['split']!='development':
                raise ValueError('Final evaluation clips must never enter training or validation')
            if row.get('training_allowed') is not True or not isinstance(row.get('training_permission'),str) or not row['training_permission'].strip():
                raise ValueError('Reviewed training_permission for audio, reference text and model adaptation is required')
            validate_rights(row,manifest)
            if row['language_switching']:
                raise ValueError('This first trainer requires single-language, manually aligned clips')
            if not math.isfinite(row['duration']) or not 0<row['duration']<=30 or not row['reference'].strip():
                raise ValueError('Training clips need nonempty reviewed text and duration <=30 seconds; nothing is truncated')
            current_groups.add(row['group_id']);current_hashes.add(row['sha256'])
            selected[split].append(row)
        if groups&current_groups or hashes&current_hashes:
            raise ValueError('Training/validation leakage: shared song/session group or recording hash')
        groups.update(current_groups);hashes.update(current_hashes)
    return selected


def plan(manifest,assignment_path,output,revision,epochs=3,learning_rate=1e-5,accumulation=8,seed=42):
    if not re.fullmatch('[a-f0-9]{40}',revision):
        raise ValueError('Pin the original Whisper Small base to an exact 40-character commit SHA')
    if not 1<=epochs<=100 or not math.isfinite(learning_rate) or not 0<learning_rate<=.01 or not 1<=accumulation<=1024:
        raise ValueError('Invalid training hyperparameters')
    assignment=json.loads(assignment_path.read_text(encoding='utf-8'))
    selected=selections(manifest,assignment)
    data=dict(version=1,base_model=BASE_MODEL,base_revision=revision,manifest=str(manifest.resolve()),
              manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),assignment=assignment,
              epochs=epochs,learning_rate=learning_rate,accumulation=accumulation,seed=seed,
              strategy='frozen encoder; full decoder; float32; batch size 1; gradient accumulation',
              coverage={split:{language:sum(row['language']==language for row in selected[split]) for language in LANGUAGES} for split in selected},
              seconds={split:sum(row['duration'] for row in selected[split]) for split in selected},
              status='planned; not trained; no singing quality claim')
    data['plan_sha256']=digest(data)
    write_new(output,data)
    return data


def load_plan(path):
    data=json.loads(path.read_text(encoding='utf-8'))
    content={k:v for k,v in data.items() if k!='plan_sha256'}
    if digest(content)!=data.get('plan_sha256') or data.get('version')!=1 or data.get('base_model')!=BASE_MODEL:
        raise ValueError('Training plan changed or is unsupported')
    manifest=Path(data['manifest'])
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=data['manifest_sha256']:
        raise ValueError('Reviewed manifest changed after planning')
    return data,selections(manifest,data['assignment'])


def hardware():
    import subprocess
    result={'training_started':False}
    try:
        result['nvidia_smi']=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free,driver_version','--format=csv,noheader'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError):
        result['nvidia_smi']='Unavailable'
    try:
        import torch
        result.update(torch=torch.__version__,cuda_runtime=torch.version.cuda,cuda_available=torch.cuda.is_available())
        if torch.cuda.is_available():
            tensor=torch.ones((8,8),device='cuda',requires_grad=True)
            (tensor@tensor).sum().backward()
            torch.cuda.synchronize()
            result.update(gpu=torch.cuda.get_device_name(0),architectures=torch.cuda.get_arch_list(),forward_backward_probe=bool(torch.isfinite(tensor.grad).all()))
        else:
            result['forward_backward_probe']=False
    except Exception as exc:
        result['error']=str(exc)
        result['forward_backward_probe']=False
    return result


def prepare_base(revision,output):
    if not re.fullmatch('[a-f0-9]{40}',revision) or output.exists():
        raise ValueError('Use a pinned base revision and a new local directory')
    from huggingface_hub import snapshot_download
    snapshot_download(BASE_MODEL,revision=revision,local_dir=output,
                      allow_patterns=['config.json','generation_config.json','model.safetensors','preprocessor_config.json',
                                      'tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','normalizer.json','special_tokens_map.json','added_tokens.json'])
    if not all((output/name).is_file() for name in ('model.safetensors','config.json','preprocessor_config.json','tokenizer_config.json')):
        raise ValueError('Incomplete local training base; required safetensors/config/tokenizer files are missing')
    write_new(output/'TRAINING_BASE.json',dict(model=BASE_MODEL,revision=revision))


def labels_for(tokenizer,text,language,decoder_start,max_length):
    tokenizer.set_prefix_tokens(language=language,task='transcribe',predict_timestamps=False)
    labels=tokenizer(text,truncation=False).input_ids
    if labels and labels[0]==decoder_start:
        labels=labels[1:]
    if not labels or len(labels)>max_length:
        raise ValueError('Reference exceeds decoder token limit; split/review the audio and text instead of truncating')
    return labels


def train(plan_path,base,output,device='cuda'):
    # All data/review/rights gates run before importing/loading any model.
    spec,selected=load_plan(plan_path)
    marker=json.loads((base/'TRAINING_BASE.json').read_text(encoding='utf-8'))
    if marker!={'model':spec['base_model'],'revision':spec['base_revision']}:
        raise ValueError('Local training base does not match the frozen plan')
    if output.exists():
        raise ValueError('Training output already exists; no checkpoint overwrite or implicit resume')
    import torch
    from transformers import WhisperProcessor, WhisperForConditionalGeneration
    if device=='cuda' and not hardware()['forward_backward_probe']:
        raise ValueError('CUDA training probe failed; use a separate CUDA-enabled PyTorch environment. No CPU fallback.')
    torch.manual_seed(spec['seed']);random.seed(spec['seed'])
    model=WhisperForConditionalGeneration.from_pretrained(base,local_files_only=True,use_safetensors=True,torch_dtype=torch.float32)
    processor=WhisperProcessor.from_pretrained(base,local_files_only=True)
    model.freeze_encoder();model.config.use_cache=False
    model.generation_config.forced_decoder_ids=None
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.to(device)
    from .adapters import FFmpegDecoder
    import wave
    import numpy as np
    decoder=FFmpegDecoder(Settings())
    features={}
    # Validate and preprocess the entire tiny/curated set before updating weights.
    # Cache on disk, not all features in RAM; never truncate audio or labels.
    with tempfile.TemporaryDirectory() as temp:
        temporary=Path(temp)
        for split,rows in selected.items():
            features[split]=[]
            for index,row in enumerate(rows):
                path=temporary/f'{split}-{index}.wav'
                info=decoder.decode(row['resolved_path'],path)
                if abs(info['duration']-row['duration'])>.1 or info['duration']>30:
                    raise ValueError('Reviewed duration mismatch or oversized training clip')
                with wave.open(str(path),'rb') as audio:
                    signal=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(np.float32)/32768
                labels=labels_for(processor.tokenizer,row['reference'],row['language'],model.config.decoder_start_token_id,model.config.max_target_positions-1)
                values=processor.feature_extractor(signal,sampling_rate=16000,return_tensors='np').input_features
                saved=temporary/f'{split}-{index}.npy';np.save(saved,values,allow_pickle=False)
                features[split].append((row,saved,labels))
                path.unlink()
        output.mkdir(parents=True)
        write_new(output/'training-plan.json',spec)
        from .worker import environment
        write_new(output/'environment.json',dict(environment=environment(),training_hardware=hardware(),device=device))
        optimizer=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=spec['learning_rate'])
        history=[]
        try:
            for epoch in range(1,spec['epochs']+1):
                model.train();optimizer.zero_grad(set_to_none=True)
                examples=list(features['train']);random.shuffle(examples)
                loss_sum=0.
                for index,(_,path,labels) in enumerate(examples):
                    values=torch.from_numpy(np.load(path,allow_pickle=False)).to(device)
                    target=torch.tensor([labels],device=device)
                    loss=model(input_features=values,labels=target).loss
                    if not torch.isfinite(loss):
                        raise ValueError('Nonfinite training loss; checkpoint not promoted')
                    # Correct scaling for the last, potentially shorter accumulation group.
                    group_start=(index//spec['accumulation'])*spec['accumulation']
                    group_size=min(spec['accumulation'],len(examples)-group_start)
                    (loss/group_size).backward();loss_sum+=loss.item()
                    if (index+1)%spec['accumulation']==0 or index+1==len(examples):
                        torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad),1.)
                        optimizer.step();optimizer.zero_grad(set_to_none=True)
                model.eval();validation=[]
                with torch.no_grad():
                    for row,path,_ in features['validation']:
                        values=torch.from_numpy(np.load(path,allow_pickle=False)).to(device)
                        generated=model.generate(values,language=row['language'],task='transcribe',return_timestamps=False,
                                                 num_beams=5,max_new_tokens=model.config.max_target_positions-4)
                        hypothesis=processor.batch_decode(generated,skip_special_tokens=True)[0]
                        complete=int(generated[0,-1])==model.config.eos_token_id
                        validation.append(dict(id=row['id'],language=row['language'],hypothesis=hypothesis,
                                               state='completed' if complete else 'failed',
                                               error=None if complete else 'Generation limit reached without end token; partial hypothesis is not scored',
                                               metrics=metrics(row['reference'],hypothesis,row['language']) if complete else None))
                checkpoint=output/f'epoch-{epoch}'
                model.save_pretrained(checkpoint,safe_serialization=True);processor.save_pretrained(checkpoint)
                write_new(checkpoint/'TRAINING_PROVENANCE.json',dict(plan_sha256=spec['plan_sha256'],epoch=epoch,
                           validation_only=True,approved_for_app=False))
                history.append(dict(epoch=epoch,mean_training_loss=loss_sum/len(examples),validation=validation))
                (output/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8')
            write_new(output/'COMPLETE.json',dict(epochs=spec['epochs'],approved_for_app=False,
                       note='Validate converted candidates against unchanged baselines and untouched final data before adoption'))
        except Exception:
            write_new(output/'FAILED.json',dict(status='failed; no promotion',completed_epochs=len(history)))
            raise


def convert(checkpoint,output):
    if output.exists() or not (checkpoint/'TRAINING_PROVENANCE.json').is_file():
        raise ValueError('Use a new destination and a training-produced local checkpoint')
    from transformers import WhisperTokenizerFast
    from ctranslate2.converters import TransformersConverter
    # A local tokenizer.json prevents faster-whisper from attempting tokenizer downloads.
    with tempfile.TemporaryDirectory() as temp:
        tokenizer=WhisperTokenizerFast.from_pretrained(checkpoint,local_files_only=True)
        tokenizer.save_pretrained(temp)
        import shutil
        shutil.copyfile(Path(temp)/'tokenizer.json',checkpoint/'tokenizer.json')
    class Converter(TransformersConverter):
        def load_model(self, model_class, model_name_or_path, **kwargs):
            kwargs['torch_dtype']=kwargs.pop('dtype',None)
            return model_class.from_pretrained(model_name_or_path,local_files_only=True,use_safetensors=True,**kwargs)
    Converter(str(checkpoint),copy_files=['tokenizer.json','preprocessor_config.json']).convert(str(output),quantization='float32',force=False)
    with (output/'model.bin').open('rb') as handle:
        revision=hashlib.file_digest(handle,'sha256').hexdigest()
    write_new(output/'READY.json',dict(model='lyriclens/fine-tuned-whisper-small',revision=revision,
               approved_for_app=False,training=json.loads((checkpoint/'TRAINING_PROVENANCE.json').read_text(encoding='utf-8'))))


def candidate_settings(settings, folder):
    from dataclasses import dataclass, field
    marker=json.loads((folder/'READY.json').read_text(encoding='utf-8'))
    if marker.get('model')!='lyriclens/fine-tuned-whisper-small' or not re.fullmatch('[a-f0-9]{64}',marker.get('revision','')):
        raise ValueError('Invalid converted candidate marker')
    with (folder/'model.bin').open('rb') as handle:
        if hashlib.file_digest(handle,'sha256').hexdigest()!=marker['revision']:
            raise ValueError('Converted model hash changed')
    if not (folder/'tokenizer.json').is_file() or not (folder/'preprocessor_config.json').is_file():
        raise ValueError('Candidate requires local tokenizer and feature extractor; no runtime download')
    @dataclass
    class CandidateSettings(Settings):
        checkpoint: Path=field(default_factory=Path)
        @property
        def model_dir(self):
            return self.checkpoint
    from dataclasses import asdict
    return CandidateSettings(**{**asdict(settings),'model_id':marker['model'],'revision':marker['revision'],
                                 'checkpoint':folder.resolve()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('hardware')
    p=sub.add_parser('prepare-base');p.add_argument('output',type=Path);p.add_argument('--revision',required=True)
    p=sub.add_parser('plan');p.add_argument('manifest',type=Path);p.add_argument('assignment',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--base-revision',required=True);p.add_argument('--epochs',type=int,default=3)
    p.add_argument('--learning-rate',type=float,default=1e-5);p.add_argument('--accumulation',type=int,default=8);p.add_argument('--seed',type=int,default=42)
    p=sub.add_parser('train');p.add_argument('plan',type=Path);p.add_argument('base',type=Path);p.add_argument('output',type=Path);p.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    p=sub.add_parser('convert');p.add_argument('checkpoint',type=Path);p.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='hardware':print(json.dumps(hardware(),indent=2))
        elif args.command=='prepare-base':prepare_base(args.revision,args.output)
        elif args.command=='plan':print(json.dumps(plan(args.manifest,args.assignment,args.output,args.base_revision,args.epochs,args.learning_rate,args.accumulation,args.seed),indent=2))
        elif args.command=='train':train(args.plan,args.base,args.output,args.device)
        else:convert(args.checkpoint,args.output)
    except (ValueError,OSError,KeyError) as exc:
        parser.error(str(exc))


if __name__=='__main__':main()
