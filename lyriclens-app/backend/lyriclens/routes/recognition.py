import queue
import shutil
import uuid
from dataclasses import replace
from fastapi import HTTPException
from ..config import LANGUAGES
from ..domain import Retranscribe, MultilingualRequest
from .. import translation as mt
from ..store import now
from ..worker import environment
from ..schemas import Job
from ..profiles import profile_settings


def register_routes(app, context):
    settings, store, worker = context.settings, context.store, context.worker
    translation_worker, get_job = context.translation_worker, context.get_job

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
            selected_model = profile_settings(settings, request.model_profile) if request.model_profile else None
            if selected_model and not (selected_model.model_dir / 'READY.json').is_file():
                raise HTTPException(409, 'Prepare the selected recognition model before retrying a passage')
            inference = {**selected_model.inference(), 'device':selected_model.device, 'compute_type':selected_model.compute_type} if selected_model else parent['inference'].copy()
            guard = request.reduce_hallucinations
            if guard is None:
                guard = parent['inference'].get('hallucination_silence_threshold') is not None
            if guard:
                guarded = replace(settings, word_timestamps=True, hallucination_silence_threshold=2.0, vad_filter=True).inference()
                inference.update(word_timestamps=True, hallucination_silence_threshold=2.0,
                                 vad_filter=True, vad_parameters=guarded['vad_parameters'])
            else:
                inference.pop('hallucination_silence_threshold', None)
                inference.pop('vad_parameters', None)
                inference['vad_filter'] = False
            identifier = str(uuid.uuid4())
            folder = settings.root / "jobs" / identifier
            folder.mkdir(parents=True)
            try:
                shutil.copyfile(settings.root / "jobs" / job_id / "original", folder / "original")
                child = {"id":identifier, "filename":parent["filename"], "sha256":parent["sha256"],
                         "bytes":parent["bytes"], "state":"queued", "stage":"Waiting for worker",
                         "requested_language":request.language,
                         "pipelines":["direct","vocals"] if request.pipeline == "both" else [request.pipeline],
                         "model_id":selected_model.model_id if selected_model else parent["model_id"],
                         "revision":selected_model.revision if selected_model else parent["revision"],
                         "model_profile":request.model_profile or parent.get("model_profile","configured"),
                         "inference":inference,
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
