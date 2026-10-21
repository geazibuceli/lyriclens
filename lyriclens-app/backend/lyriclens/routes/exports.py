import json
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from ..domain import text_of, srt, lrc
from .. import translation as mt


def register_routes(app, context):
    settings, store, worker = context.settings, context.store, context.worker
    translation_worker, get_job = context.translation_worker, context.get_job

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
        elif format == "lrc":
            content, media = lrc(segments), "text/plain"
        else:
            raise HTTPException(422, "Use txt, json, srt, or lrc")
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
