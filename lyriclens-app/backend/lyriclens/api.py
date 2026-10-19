import asyncio
import hashlib
import json
import logging
import queue
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from .config import Settings, LANGUAGES
from .domain import Edit, Retranscribe, TranslationRequest, TranslationEdit, MultilingualRequest, validate_segments, text_of, srt
from . import translation as mt
from .store import Store, now
from .worker import Worker, environment
from .limits import UploadLimit
from .schemas import Job, ModelReadiness
from .profiles import profile_settings, available_profiles
from . import maintenance
from . import backups
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool


def create_app(settings=None, decoder=None, transcriber=None, separator=None, translator=None):
    settings = settings or Settings()
    store = Store(settings.root)
    worker = Worker(settings, store, decoder, transcriber, separator)
    translation_worker = mt.TranslationWorker(settings,store,translator)

    @asynccontextmanager
    async def lifespan(app):
        # Exclusive process lock enforces one server instance per data directory.
        lock_path = settings.root / "instance.lock"
        handle = lock_path.open("a+b")
        started = False
        try:
            if __import__("os").name == "nt":
                import msvcrt
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            worker.start()
            translation_worker.start()
            started = True
            yield
        finally:
            if started:
                translation_worker.stop()
                worker.stop()
            handle.close()

    app = FastAPI(title="LyricLens", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker
    app.state.translation_worker = translation_worker
    app.add_middleware(UploadLimit, max_bytes=settings.max_bytes)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5181", "http://127.0.0.1:5181"],
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])

    def get_job(job_id):
        job = store.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return job

    @app.get('/api/translation')
    def translation_status():
        import importlib.util
        dependencies = all(importlib.util.find_spec(name) is not None for name in ['ctranslate2','transformers','sentencepiece'])
        return dict(model_id=mt.MODEL,revision=mt.REVISION,languages=LANGUAGES,
                    prepared=translation_worker.injected or mt.prepared(settings),
                    dependencies_available=translation_worker.injected or dependencies,device='cpu',compute_type='int8')

    @app.post('/api/jobs/{job_id}/translate',status_code=202,response_model=Job)
    def translate_job(job_id: str, request: TranslationRequest):
        if request.source_language not in LANGUAGES or request.target_language not in LANGUAGES:
            raise HTTPException(422,'Choose a supported source and target language')
        with store.lock:
            job = get_job(job_id)
            if job['state'] in {'queued','processing'} or mt.has_active(job):
                raise HTTPException(409,'Wait for active transcription or translation to finish')
            try:
                segments = mt.source_segments(job,request.pipeline)
            except ValueError as exc:
                raise HTTPException(409,str(exc)) from None
            if not any(s['text'].strip() for s in segments):
                raise HTTPException(422,'There is no text to translate. Review or edit the transcript first.')
            source_languages = sorted({s.get('language') or request.source_language for s in segments if s['text'].strip()})
            if source_languages==[request.target_language]:
                raise HTTPException(422,'Choose a target language different from at least one source language')
            if len(segments)>1000 or sum(len(s['text']) for s in segments)>100000:
                raise HTTPException(422,'Translation supports up to 1000 segments and 100000 source characters')
            readiness = translation_status()
            if not readiness['prepared'] or not readiness['dependencies_available']:
                raise HTTPException(409,'Prepare optional translation dependencies and run python -m lyriclens.models translation-download first.')
            name = mt.key(request.pipeline,request.target_language)
            previous = job.get('translations',{}).get(name)
            job.setdefault('translations',{})[name] = dict(state='queued',pipeline=request.pipeline,
                source_language=request.source_language,target_language=request.target_language,
                source_languages=source_languages,
                source_segments=segments,source_fingerprint=mt.fingerprint(segments),
                source_version='edited' if job['results'][request.pipeline].get('edited') is not None else 'original',
                segments=[],edited=None,stale=False,created_at=now(),completed_segments=0,cancel_requested=False,
                model_id=mt.MODEL,revision=mt.REVISION,device='cpu',compute_type='int8',
                settings={'beam_size':4,'max_input_tokens':512,'max_output_tokens':512},
                warning='Machine translation for understanding; errors may propagate from transcription. Rhyme and singability are not preserved.')
            store.put(job)
            try:
                translation_worker.queue.put_nowait((job_id,name))
            except queue.Full:
                if previous is None:
                    del job['translations'][name]
                else:
                    job['translations'][name] = previous
                store.put(job)
                raise HTTPException(429,'Local translation queue is full. Try again after a translation finishes.') from None
            return job

    @app.post('/api/jobs/{job_id}/translation/cancel',response_model=Job)
    def cancel_translation(job_id: str, request: TranslationRequest):
        with store.lock:
            job = get_job(job_id)
            item = job.get('translations',{}).get(mt.key(request.pipeline,request.target_language))
            if not item:
                raise HTTPException(404,'Translation not found')
            if item['state'] in mt.ACTIVE:
                item['cancel_requested'] = True
                store.put(job)
            return job

    @app.post('/api/jobs/{job_id}/resume', status_code=202, response_model=Job)
    def resume_job(job_id: str):
        with store.lock:
            job = get_job(job_id)
            if job.get('imported_snapshot'):
                raise HTTPException(409, 'Imported ASR snapshots are read-only for resume; upload the recording as a new job to recognize it')
            if job['state'] not in {'interrupted', 'canceled', 'failed', 'completed'} or mt.has_active(job):
                raise HTTPException(409, 'Only stopped jobs without active translations can be resumed')
            if all(job['results'].get(p, {}).get('state') == 'completed' for p in job['pipelines']):
                raise HTTPException(409, 'All recognition routes are already completed')
            original = settings.root/'jobs'/job_id/'original'
            if not original.is_file():
                raise HTTPException(409, 'Original recording is unavailable; upload it again')
            with original.open('rb') as handle:
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
            if digest != job['sha256']:
                raise HTTPException(409, 'Original recording changed; upload it as a new job')
            previous = json.loads(json.dumps(job))
            job.update(state='queued',stage='Waiting to resume unfinished routes',cancel_requested=False,
                       error=None,completed_at=None,resume_count=job.get('resume_count',0)+1)
            store.put(job)
            try:
                worker.queue.put_nowait(job_id)
            except queue.Full:
                store.put(previous)
                raise HTTPException(429, 'Local queue is full; try again later') from None
            return job

    @app.post('/api/jobs/{job_id}/translation/resume',status_code=202,response_model=Job)
    def resume_translation(job_id: str, request: TranslationRequest):
        with store.lock:
            job = get_job(job_id)
            name = mt.key(request.pipeline,request.target_language)
            item = job.get('translations',{}).get(name)
            if not item or item['state'] not in {'interrupted','canceled','failed'}:
                raise HTTPException(409, 'No stopped translation to resume')
            if request.source_language != item['source_language']:
                raise HTTPException(409, 'Resume uses the saved source language; create a new translation to change it')
            if job['state'] in {'queued','processing'} or mt.has_active(job) or mt.is_stale(job,item):
                raise HTTPException(409, 'Wait for active tasks or translate the changed source again')
            readiness = translation_status()
            if not readiness['prepared'] or not readiness['dependencies_available']:
                raise HTTPException(409, 'Prepare the local translation model and dependencies first')
            previous = json.loads(json.dumps(job))
            item.update(state='queued',cancel_requested=False,error=None,completed_at=None,
                        completed_segments=len(item.get('segments',[])),resume_count=item.get('resume_count',0)+1)
            store.put(job)
            try:
                translation_worker.queue.put_nowait((job_id,name))
            except queue.Full:
                store.put(previous)
                raise HTTPException(429, 'Local translation queue is full') from None
            return job

    @app.put('/api/jobs/{job_id}/translation',response_model=Job)
    def edit_translation(job_id: str, edit: TranslationEdit):
        with store.lock:
            job = get_job(job_id)
            item = job.get('translations',{}).get(mt.key(edit.pipeline,edit.target_language))
            if not item or item['state']!='completed':
                raise HTTPException(409,'No completed translation for this language')
            if mt.is_stale(job,item):
                raise HTTPException(409,'The source transcript changed. Translate the current text before editing or exporting.')
            if len(edit.texts)!=len(item['segments']):
                raise HTTPException(422,'Keep one translation per source segment; timestamps are inherited from the source')
            if sum(len(text) for text in edit.texts)>100000:
                raise HTTPException(422,'Translation edits support up to 100000 characters')
            item['edited'] = [{**s,'text':text} for s,text in zip(item['segments'],edit.texts)]
            item['edited_at'] = now()
            store.put(job)
            return job

    @app.get("/api/health")
    def health():
        return {"status": "ok", "worker_alive": worker.thread.is_alive(), "single_instance": True}

    @app.get("/api/models", response_model=ModelReadiness)
    def models():
        return {"model_id": settings.model_id, "revision": settings.revision,
                "prepared": (settings.model_dir / "READY.json").exists(),
                "separation_prepared": (settings.root / "separation-models" / "955717e8-8726e21a.th").exists(),
                "ffmpeg_available": shutil.which(settings.ffmpeg) is not None,
                "languages": LANGUAGES, "max_bytes": settings.max_bytes, "max_seconds": settings.max_seconds,
                "device": settings.device, "compute_type": settings.compute_type,
                "profiles": available_profiles(settings)}

    @app.get('/api/diagnostics')
    def diagnostics():
        return maintenance.diagnostics(settings)

    @app.get('/api/jobs/{job_id}/backup')
    def backup_job(job_id: str):
        with store.lock:
            job=get_job(job_id)
            if job['state'] in {'queued','processing'} or mt.has_active(job):
                raise HTTPException(409, 'Stop active work before downloading a consistent backup')
            try:
                archive=backups.create(settings,job)
            except (ValueError,OSError) as exc:
                raise HTTPException(409, str(exc) if isinstance(exc,ValueError) else 'Backup files unavailable') from None
        return FileResponse(archive,media_type='application/zip',filename=f'{job_id}.lyriclens.zip',
                            background=BackgroundTask(archive.unlink,missing_ok=True))

    @app.post('/api/backups/restore',status_code=201,response_model=Job)
    async def restore_backup(file: Annotated[UploadFile,File()]):
        import tempfile
        import zipfile
        try:
            with tempfile.TemporaryFile() as source:
                total=0
                while chunk:=await file.read(65536):
                    total+=len(chunk)
                    if total>settings.max_bytes+3*backups.METADATA_LIMIT+65536:
                        raise HTTPException(413,'Backup exceeds supported size')
                    source.write(chunk)
                source.seek(0)
                return await run_in_threadpool(backups.restore,settings,store,source)
        except (ValueError,KeyError,TypeError,RecursionError,zipfile.BadZipFile,RuntimeError,OverflowError,NotImplementedError):
            raise HTTPException(422,'Invalid backup. Check format, metadata, sizes and recording hash; no existing job was replaced.') from None
        except OSError:
            raise HTTPException(409,'Backup could not be restored. Check local storage and permissions.') from None
        finally:
            await file.close()

    @app.get('/api/storage')
    def storage():
        with store.lock:
            return maintenance.storage(settings, store.list())

    @app.post('/api/jobs/{job_id}/cleanup-cache')
    def cleanup_cache(job_id: str):
        with store.lock:
            job = get_job(job_id)
            if job['state'] in {'queued','processing'} or mt.has_active(job):
                raise HTTPException(409, 'Wait for transcription and translation to stop before clearing cache')
            try:
                return maintenance.cleanup(settings, job_id)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            except OSError:
                raise HTTPException(409, 'Some cache files are in use or unavailable. Stop playback and retry; originals and saved text are preserved.') from None

    @app.get('/api/jobs/{job_id}/waveform')
    def waveform(job_id: str):
        import tempfile
        import wave
        import math
        from array import array
        import sys
        job = get_job(job_id)
        if job['state'] in {'queued','processing'}:
            raise HTTPException(409, 'Wait for recognition to stop before loading the waveform')
        try:
            with tempfile.TemporaryDirectory() as tmp:
                decoded = Path(tmp)/'waveform.wav'
                worker.decoder.decode(settings.root/'jobs'/job_id/'original', decoded)
                with wave.open(str(decoded), 'rb') as audio:
                    if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
                        raise ValueError('Waveform requires mono PCM16 audio')
                    frames, rate = audio.getnframes(), audio.getframerate()
                    chunk = max(1, math.ceil(frames/1200))
                    peaks = []
                    while data := audio.readframes(chunk):
                        samples = array('h', data)
                        if sys.byteorder != 'little':
                            samples.byteswap()
                        peaks.append(max((abs(value) for value in samples), default=0)/32768)
                    return dict(duration=frames/rate, peaks=peaks, method='Peak absolute mono PCM16 amplitude; full original timeline, at most 1200 bins')
        except (ValueError, OSError, wave.Error, EOFError):
            raise HTTPException(409, 'Waveform could not be decoded. Check the original recording and FFmpeg setup.') from None

    @app.post("/api/jobs", status_code=202, response_model=Job)
    async def create_job(file: Annotated[UploadFile, File()], language: Annotated[str, Form()] = "auto",
                         pipeline: Annotated[str, Form()] = "direct",
                         model_profile: Annotated[str, Form()] = "configured"):
        if language not in {"auto", *LANGUAGES} or pipeline not in {"direct", "vocals", "both"}:
            raise HTTPException(422, "Unsupported language or pipeline")
        try:
            selected_model = profile_settings(settings,model_profile)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        filename = (file.filename or "audio").replace("\\", "/").split("/")[-1][:200]
        if Path(filename).suffix.lower() not in {".wav", ".mp3", ".flac", ".m4a", ".mp4"}:
            raise HTTPException(415, "Use WAV, MP3, FLAC, M4A, or MP4")
        job_id = str(uuid.uuid4())
        folder = settings.root / "jobs" / job_id
        folder.mkdir(parents=True)
        size, digest = 0, hashlib.sha256()
        try:
            with (folder / "original").open("wb") as out:
                while chunk := await file.read(65536):
                    size += len(chunk)
                    if size > settings.max_bytes:
                        raise HTTPException(413, "Upload exceeds configured size limit")
                    digest.update(chunk)
                    out.write(chunk)
            if not size:
                raise HTTPException(422, "Upload is empty")
            job = {"id": job_id, "filename": filename, "sha256": digest.hexdigest(), "bytes": size,
                   "state": "queued", "stage": "Waiting for worker", "requested_language": language,
                   "pipelines": ["direct", "vocals"] if pipeline == "both" else [pipeline],
                   "model_id": selected_model.model_id, "revision": selected_model.revision,"model_profile":model_profile,
                   "inference": {**selected_model.inference(), "device": selected_model.device, "compute_type": selected_model.compute_type},
                   "environment": environment(), "created_at": now(), "results": {}, "cancel_requested": False}
            store.put(job)
            try:
                worker.queue.put_nowait(job_id)
            except queue.Full:
                store.delete(job_id)
                raise HTTPException(429, "Local queue is full. Try again after a job finishes.") from None
            return job
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        finally:
            await file.close()

    @app.get("/api/jobs", response_model=list[Job])
    def jobs():
        return store.list()

    @app.get("/api/jobs/{job_id}", response_model=Job)
    def read_job(job_id: str):
        return get_job(job_id)

    @app.get("/api/jobs/{job_id}/audio")
    def audio(job_id: str):
        get_job(job_id)
        return FileResponse(settings.root / "jobs" / job_id / "original", filename="clip" + Path(get_job(job_id)["filename"]).suffix)

    @app.post("/api/jobs/{job_id}/retranscribe", status_code=202, response_model=Job)
    def retranscribe(job_id: str, request: Retranscribe):
        if request.language not in LANGUAGES:
            raise HTTPException(422, "Select one of the seven target languages for a region override")
        with store.lock:
            parent = get_job(job_id)
            if parent["state"] in {"queued", "processing"} or "audio" not in parent:
                raise HTTPException(409, "Wait for a decoded job before selecting a region")
            duration = parent["audio"]["duration"]
            if request.end > duration:
                raise HTTPException(422, "Region must be within the original clip")
            identifier = str(uuid.uuid4())
            folder = settings.root / "jobs" / identifier
            folder.mkdir(parents=True)
            try:
                shutil.copyfile(settings.root / "jobs" / job_id / "original", folder / "original")
                child = {"id":identifier, "filename":parent["filename"], "sha256":parent["sha256"],
                         "bytes":parent["bytes"], "state":"queued", "stage":"Waiting for worker",
                         "requested_language":request.language,
                         "pipelines":["direct","vocals"] if request.pipeline == "both" else [request.pipeline],
                         "model_id":parent["model_id"], "revision":parent["revision"],
                         "model_profile":parent.get("model_profile","configured"),
                         "inference":parent["inference"].copy(),
                         "environment":environment(), "created_at":now(), "results":{}, "cancel_requested":False,
                         "source_job_id":job_id,
                         "region":{"selected_start":request.start,"selected_end":request.end,
                                   "start":max(0,request.start-request.context_seconds),
                                   "end":min(duration,request.end+request.context_seconds),
                                   "method":"user-selected language and region with surrounding audio context"}}
                store.put(child)
                worker.queue.put_nowait(identifier)
                return child
            except queue.Full:
                store.delete(identifier)
                shutil.rmtree(folder,ignore_errors=True)
                raise HTTPException(429,"Local queue is full") from None
            except Exception:
                store.delete(identifier)
                shutil.rmtree(folder,ignore_errors=True)
                raise

    @app.post('/api/jobs/{job_id}/retranscribe-multilingual',status_code=202,response_model=Job)
    def retranscribe_multilingual(job_id: str, request: MultilingualRequest):
        if request.default_language not in {'auto',*LANGUAGES}:
            raise HTTPException(422,'Select a supported fallback language or automatic detection')
        with store.lock:
            parent = get_job(job_id)
            if parent['state'] in {'queued','processing'}:
                raise HTTPException(409,'Wait for transcription to finish')
            try:
                segments = mt.source_segments(parent,request.pipeline)
            except ValueError as exc:
                raise HTTPException(409,str(exc)) from None
            if len({s.get('language') for s in segments if s.get('language')})<2:
                raise HTTPException(422,'Save at least two different passage language labels first')
            if len(segments)>1000:
                raise HTTPException(422,'Use at most 1000 saved passages')
            previous_end = 0
            for segment in segments:
                if segment['start']<previous_end:
                    raise HTTPException(422,'Saved passages overlap. Adjust their start/end times before multilingual recognition.')
                previous_end = segment['end']
            identifier = str(uuid.uuid4())
            jobs_root = (settings.root/'jobs').resolve()
            folder = (jobs_root/identifier).resolve()
            if folder.parent!=jobs_root:
                raise HTTPException(409,'Job location unavailable')
            folder.mkdir(parents=True)
            try:
                shutil.copyfile(settings.root/'jobs'/job_id/'original',folder/'original')
                child = dict(id=identifier,filename=parent['filename'],sha256=parent['sha256'],bytes=parent['bytes'],
                    state='queued',stage='Waiting for worker',requested_language='mixed',pipelines=[request.pipeline],
                    model_id=parent['model_id'],revision=parent['revision'],model_profile=parent.get('model_profile','configured'),
                    inference=parent['inference'].copy(),environment=environment(),created_at=now(),results={},cancel_requested=False,
                    source_job_id=job_id,source_fingerprint=mt.fingerprint(segments),
                    language_plan=[dict(start=s['start'],end=s['end'],language=s.get('language') or request.default_language) for s in segments],
                    language_plan_method='User-instructed saved passages; unlabeled gaps are not transcribed; no automatic code-switch detection')
                store.put(child)
                worker.queue.put_nowait(identifier)
                return child
            except Exception as exc:
                store.delete(identifier)
                shutil.rmtree(folder,ignore_errors=True)
                if isinstance(exc,queue.Full):
                    raise HTTPException(429,'Local queue is full') from None
                raise

    @app.put("/api/jobs/{job_id}/edit", response_model=Job)
    def edit_job(job_id: str, edit: Edit):
        with store.lock:
            job = get_job(job_id)
            if job["state"] in {"queued", "processing"}:
                raise HTTPException(409, "Wait for processing to finish")
            result = job["results"].get(edit.pipeline)
            if not result or result["state"] != "completed":
                raise HTTPException(409, "No completed result for this pipeline")
            try:
                result["edited"] = validate_segments([{**s.model_dump(),'language_source':'user instruction' if s.language else None} for s in edit.segments], job["audio"]["duration"])
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            result["edited_at"] = now()
            for item in job.get('translations',{}).values():
                if item['pipeline']==edit.pipeline:
                    item['stale'] = mt.is_stale(job,item)
            store.put(job)
            return job

    @app.post("/api/jobs/{job_id}/cancel", response_model=Job)
    def cancel(job_id: str):
        with store.lock:
            job = get_job(job_id)
            if job["state"] not in {"queued", "processing"}:
                return job
            return store.update(job_id, cancel_requested=True, stage="Cancellation requested; waiting for active operation")

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete(job_id: str):
        with store.lock:
            job = get_job(job_id)
            if job["state"] in {"queued", "processing"}:
                raise HTTPException(409, "Cancel and wait for the job to stop before deletion")
            if mt.has_active(job):
                raise HTTPException(409,'Cancel and wait for translation to stop before deletion')
            jobs_root = (settings.root / "jobs").resolve()
            folder = (jobs_root / job_id).resolve()
            if folder.parent != jobs_root:
                raise HTTPException(409, "Job audio location is unavailable for deletion")
            for attempt in range(5):
                try:
                    shutil.rmtree(folder)
                    break
                except FileNotFoundError:
                    # A prior partial deletion may already have removed the folder.
                    if not folder.exists():
                        break
                    if attempt == 4:
                        raise HTTPException(409, "Audio files changed during deletion. Please retry.") from None
                except PermissionError:
                    if attempt == 4:
                        raise HTTPException(409, "Audio is still in use. Stop playback in other tabs or players, then retry deletion.") from None
                except OSError:
                    logging.getLogger("lyriclens").exception("Could not delete job audio")
                    raise HTTPException(500, "Could not delete audio files. Check file permissions and retry.") from None
                time.sleep(.1 * 2**attempt)
            store.delete(job_id)

    @app.get("/api/jobs/{job_id}/export")
    def export(job_id: str, pipeline: str = "direct", format: str = "txt", original: bool = False, translation: str | None = None, bilingual: bool = False):
        if bilingual and (translation is None or format not in {'txt','srt'}):
            raise HTTPException(422, 'Bilingual export requires a translation and TXT or SRT format')
        job = get_job(job_id)
        result = job["results"].get(pipeline)
        if not result or result["state"] != "completed":
            raise HTTPException(409, "No completed result for this pipeline")
        segments = result["original"] if original or result["edited"] is None else result["edited"]
        exported = job
        suffix = pipeline
        if translation is not None:
            item = job.get('translations',{}).get(mt.key(pipeline,translation))
            if not item or item['state']!='completed':
                raise HTTPException(409,'No completed translation for this language')
            if mt.is_stale(job,item):
                raise HTTPException(409,'The source transcript changed. Translate the current text before exporting.')
            segments = item['edited'] if item.get('edited') is not None and not original else item['segments']
            exported = item
            suffix = f'{pipeline}-translation-{translation}'
            if bilingual:
                if len(segments) != len(item['source_segments']):
                    raise HTTPException(409, 'Translation/source segment alignment is unavailable')
                segments = [{**segment,'text':source['text']+'\n'+segment['text']}
                            for source,segment in zip(item['source_segments'],segments)]
                suffix += '-bilingual'
        if format == "json":
            content, media = json.dumps(exported, ensure_ascii=False, indent=2), "application/json"
        elif format == "txt":
            content, media = text_of(segments), "text/plain"
        elif format == "srt":
            content, media = srt(segments), "application/x-subrip"
        else:
            raise HTTPException(422, "Use txt, json, or srt")
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{job_id}-{suffix}.{format}"'})

    @app.get("/api/jobs/{job_id}/raw")
    def raw(job_id: str, pipeline: str = "direct"):
        get_job(job_id)
        if pipeline not in {"direct", "vocals"}:
            raise HTTPException(422, "Unsupported pipeline")
        path = settings.root / "jobs" / job_id / f"{pipeline}-raw.json"
        if not path.exists():
            raise HTTPException(404, "Raw model response unavailable")
        return FileResponse(path, media_type="application/json", filename=f"{pipeline}-raw.json")

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
