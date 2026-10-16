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
from .domain import Edit, Retranscribe, validate_segments, text_of, srt
from .store import Store, now
from .worker import Worker, environment
from .limits import UploadLimit
from .schemas import Job, ModelReadiness
from .profiles import profile_settings, available_profiles


def create_app(settings=None, decoder=None, transcriber=None, separator=None):
    settings = settings or Settings()
    store = Store(settings.root)
    worker = Worker(settings, store, decoder, transcriber, separator)

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
            started = True
            yield
        finally:
            if started:
                worker.stop()
            handle.close()

    app = FastAPI(title="LyricLens", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker
    app.add_middleware(UploadLimit, max_bytes=settings.max_bytes)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5181", "http://127.0.0.1:5181"],
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])

    def get_job(job_id):
        job = store.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
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
                result["edited"] = validate_segments([s.model_dump() for s in edit.segments], job["audio"]["duration"])
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            result["edited_at"] = now()
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
    def export(job_id: str, pipeline: str = "direct", format: str = "txt", original: bool = False):
        job = get_job(job_id)
        result = job["results"].get(pipeline)
        if not result or result["state"] != "completed":
            raise HTTPException(409, "No completed result for this pipeline")
        segments = result["original"] if original or result["edited"] is None else result["edited"]
        if format == "json":
            content, media = json.dumps(job, ensure_ascii=False, indent=2), "application/json"
        elif format == "txt":
            content, media = text_of(segments), "text/plain"
        elif format == "srt":
            content, media = srt(segments), "application/x-subrip"
        else:
            raise HTTPException(422, "Use txt, json, or srt")
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{job_id}-{pipeline}.{format}"'})

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
