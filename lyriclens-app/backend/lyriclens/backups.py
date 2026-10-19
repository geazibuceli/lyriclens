"""Versioned per-job archives. Never extract paths or enqueue imported work."""
import hashlib
import json
import math
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path
from .domain import validate_segments
from .schemas import Job
from .maintenance import folder_for, linked
from .store import now
from .config import LANGUAGES

MEMBERS={'backup.json','original','direct-raw.json','vocals-raw.json'}
METADATA_LIMIT=32*1024*1024


def reject_nonfinite(value):
    raise ValueError('Nonfinite backup JSON value')


def create(settings, job):
    folder=folder_for(settings,job['id'])
    descriptor, name = tempfile.mkstemp(suffix='.lyriclens.zip')
    import os
    os.close(descriptor)
    target=Path(name)
    try:
        if linked(folder/'original'):
            raise ValueError('Linked recordings cannot be backed up')
        with (folder/'original').open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=job['sha256']:
                raise ValueError('Original recording changed; backup refused')
        document=json.dumps(dict(format='lyriclens-job',version=1,job=job),ensure_ascii=False).encode()
        if len(document)>METADATA_LIMIT:
            raise ValueError('Job metadata exceeds backup limit')
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('backup.json',document)
            archive.write(folder/'original','original')
            for pipeline in ('direct','vocals'):
                raw=folder/f'{pipeline}-raw.json'
                if raw.exists():
                    if linked(raw) or raw.stat().st_size>METADATA_LIMIT:
                        raise ValueError('Raw response is linked or exceeds backup limit')
                    archive.write(raw,raw.name)
        if target.stat().st_size>settings.max_bytes+3*METADATA_LIMIT+65536:
            raise ValueError('Backup exceeds supported archive size')
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def restore(settings, store, source):
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        names=[entry.filename for entry in entries]
        if len(names)!=len(set(names)) or not {'backup.json','original'}.issubset(names) or not set(names)<=MEMBERS:
            raise ValueError('Invalid backup members; arbitrary paths and duplicate entries are rejected')
        for entry in entries:
            limit=settings.max_bytes if entry.filename=='original' else METADATA_LIMIT
            if entry.file_size>limit or entry.file_size<0 or entry.flag_bits&1 or stat.S_ISLNK(entry.external_attr>>16):
                raise ValueError('Oversized, encrypted or linked backup member')
        document=json.loads(archive.read('backup.json'),parse_constant=reject_nonfinite)
        if not isinstance(document,dict) or document.get('format')!='lyriclens-job' or document.get('version')!=1:
            raise ValueError('Unsupported backup format/version')
        job=document['job']
        Job.model_validate(job)
        if job.get('error') is not None and not isinstance(job['error'],str):
            raise ValueError('Invalid job error metadata')
        if job.get('model_profile') is not None and not isinstance(job['model_profile'],str):
            raise ValueError('Invalid model profile metadata')
        if 'audio' in job and not isinstance(job['audio'],dict):
            raise ValueError('Invalid audio metadata')
        duration=job.get('audio',{}).get('duration')
        has_segments=any(r.get('original') or r.get('edited') for r in job['results'].values())
        if (has_segments or 'audio' in job) and (not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0<duration<=settings.max_seconds):
            raise ValueError('Backup duration unavailable or outside configured limit')
        for result in job['results'].values():
            for field in ('original','edited'):
                if result.get(field) is not None:
                    if len(result[field])>1000:
                        raise ValueError('Too many backup segments')
                    result[field]=validate_segments(result[field],duration)
        if not isinstance(job.get('translations',{}),dict):
            raise ValueError('Invalid translation map')
        for key,translation in job.get('translations',{}).items():
            if not isinstance(translation,dict):
                raise ValueError('Invalid translation object')
            if translation.get('source_language') not in LANGUAGES or translation.get('target_language') not in LANGUAGES or translation.get('pipeline') not in {'direct','vocals'} or key!=f"{translation['pipeline']}:{translation['target_language']}" or translation.get('state') not in {'queued','processing','interrupted','completed','failed','canceled'}:
                raise ValueError('Invalid translation metadata')
            for field in ('source_version','source_fingerprint','warning'):
                if not isinstance(translation.get(field),str):
                    raise ValueError('Invalid translation text metadata')
            if translation.get('error') is not None and not isinstance(translation['error'],str):
                raise ValueError('Invalid translation error metadata')
            if not isinstance(translation.get('completed_segments'),int) or translation['completed_segments']<0:
                raise ValueError('Invalid translation progress metadata')
            if not isinstance(translation.get('stale'),bool):
                raise ValueError('Invalid translation state metadata')
            if 'source_languages' in translation and (not isinstance(translation['source_languages'],list) or any(language not in LANGUAGES for language in translation['source_languages'])):
                raise ValueError('Invalid source-language list')
            for field in ('source_segments','segments','edited'):
                if translation.get(field) is not None:
                    if len(translation[field])>1000:
                        raise ValueError('Too many translation segments')
                    translation[field]=validate_segments(translation[field],duration)
            if len(translation.get('segments',[]))>len(translation['source_segments']):
                raise ValueError('Translation checkpoint exceeds source length')
            if translation['state']=='completed' and len(translation['segments'])!=len(translation['source_segments']):
                raise ValueError('Completed translation/source alignment mismatch')
            if translation.get('edited') is not None and len(translation['edited'])!=len(translation['segments']):
                raise ValueError('Edited translation alignment mismatch')
            if translation['completed_segments']!=len(translation['segments']):
                # Older interrupted checkpoints did not persist their partial text.
                translation['completed_segments']=len(translation['segments'])
            if translation['state'] in {'queued','processing'}:
                translation.update(state='interrupted',cancel_requested=False,error='Imported checkpoint; resume explicitly')
        # Imports are snapshots, never executable jobs: drop instructions that could
        # become filesystem/model selectors and disable resume of imported ASR.
        original_id=job['id']
        identifier=str(uuid.uuid4())
        job.update(id=identifier,created_at=now(),restored_from=original_id,restored_at=now(),
                   imported_snapshot=True,cancel_requested=False)
        if job['state'] in {'queued','processing'}:
            job.update(state='interrupted',stage='Imported snapshot; no processing started')
        folder=folder_for(settings,identifier)
        folder.mkdir(parents=True)
        try:
            digest=hashlib.sha256()
            with archive.open('original') as handle, (folder/'original').open('wb') as out:
                total=0
                while chunk:=handle.read(65536):
                    total+=len(chunk)
                    if total>settings.max_bytes:
                        raise ValueError('Recording exceeds configured limit')
                    digest.update(chunk);out.write(chunk)
            if not total or total!=job['bytes'] or digest.hexdigest()!=job['sha256']:
                raise ValueError('Backup original hash/size mismatch')
            for name in ('direct-raw.json','vocals-raw.json'):
                if name in names:
                    (folder/name).write_bytes(archive.read(name))
            store.put(job)
            return job
        except Exception:
            shutil.rmtree(folder)
            raise
