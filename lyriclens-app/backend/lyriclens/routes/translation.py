import json
import queue
from fastapi import HTTPException
from ..config import LANGUAGES
from ..domain import TranslationRequest, TranslationEdit
from .. import translation as mt
from ..store import now
from ..schemas import Job


def register_routes(app, context):
    settings, store, worker = context.settings, context.store, context.worker
    translation_worker, get_job = context.translation_worker, context.get_job

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
