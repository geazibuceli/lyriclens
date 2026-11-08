import hashlib
import json
import logging
import queue
from dataclasses import replace
import shutil
import time
import uuid
import wave
from pathlib import Path
from typing import Annotated
from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from ..config import LANGUAGES
from ..domain import Edit, RenameJob, validate_segments
from .. import translation as mt
from ..store import now
from ..worker import environment
from ..schemas import Job
from ..profiles import profile_settings
from ..maintenance import folder_for, linked


def register_routes(app, context):
    settings, store, worker = context.settings, context.store, context.worker
    translation_worker, get_job = context.translation_worker, context.get_job

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

    @app.post("/api/jobs", status_code=202, response_model=Job)
    async def create_job(file: Annotated[UploadFile, File()], language: Annotated[str, Form()] = "auto",
                         pipeline: Annotated[str, Form()] = "direct",
                         model_profile: Annotated[str, Form()] = "configured",
                         reduce_hallucinations: Annotated[bool, Form()] = False):
        if language not in {"auto", *LANGUAGES} or pipeline not in {"direct", "vocals", "both"}:
            raise HTTPException(422, "Unsupported language or pipeline")
        try:
            selected_model = profile_settings(settings,model_profile)
            if reduce_hallucinations:
                selected_model = replace(selected_model, word_timestamps=True, hallucination_silence_threshold=2.0, vad_filter=True)
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

    @app.patch("/api/jobs/{job_id}", response_model=Job)
    def rename_job(job_id: str, edit: RenameJob):
        with store.lock:
            get_job(job_id)
            return store.update(job_id, title=edit.title.strip())

    @app.get("/api/jobs/{job_id}/audio")
    def audio(job_id: str, compatible: bool = False, pipeline: str = 'direct'):
        if pipeline not in {'direct', 'vocals'}:
            raise HTTPException(422, 'Unsupported playback route')
        with store.lock:
            job = get_job(job_id)
            folder = folder_for(settings, job_id)
            if pipeline == 'vocals':
                source = folder / 'vocals-16k.wav'
                if job['results'].get('vocals', {}).get('state') != 'completed' or not source.is_file() or linked(source):
                    raise HTTPException(404, 'Isolated audio is unavailable. Its cache may have been cleared; use original audio or run vocal separation again.')
                try:
                    with wave.open(str(source), 'rb') as stream:
                        duration = stream.getnframes() / stream.getframerate()
                    if abs(duration - job.get('audio', {}).get('duration', 0)) > .1:
                        raise ValueError('Timeline mismatch')
                except (ValueError, OSError, wave.Error, EOFError):
                    raise HTTPException(409, 'Isolated audio does not cover the full recording timeline. Use original audio for this result.') from None
                return FileResponse(source, media_type='audio/wav', filename='isolated-vocals.wav',
                                    content_disposition_type='inline')
            source = folder / 'original'
            if not source.is_file() or linked(source):
                raise HTTPException(404, 'Original audio is unavailable. Upload the recording again.')
            suffix = Path(job['filename']).suffix.lower()
            if compatible:
                target = folder / 'playback.wav'
                temporary = folder / 'playback-pending.wav'
                if any(path.exists() and linked(path) for path in (target, temporary)):
                    raise HTTPException(409, 'Playback cache is unavailable.')
                if not target.exists():
                    try:
                        worker.decoder.decode(source, temporary)
                        temporary.replace(target)
                    except (ValueError, OSError) as exc:
                        temporary.unlink(missing_ok=True)
                        raise HTTPException(422, 'Compatible audio could not be prepared. Check FFmpeg and the original recording.') from exc
                source, suffix = target, '.wav'
            media = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.flac': 'audio/flac',
                     '.m4a': 'audio/mp4', '.mp4': 'video/mp4'}.get(suffix, 'application/octet-stream')
            return FileResponse(source, media_type=media, filename='clip' + suffix,
                                content_disposition_type='inline')

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
