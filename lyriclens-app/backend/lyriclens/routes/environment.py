import shutil
from pathlib import Path
from fastapi import HTTPException
from ..config import LANGUAGES
from .. import translation as mt
from ..schemas import ModelReadiness
from ..profiles import available_profiles
from .. import maintenance


def register_routes(app, context):
    settings, store, worker = context.settings, context.store, context.worker
    translation_worker, get_job = context.translation_worker, context.get_job

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
