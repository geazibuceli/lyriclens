from typing import Annotated
from fastapi import File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from .. import translation as mt
from ..schemas import Job
from .. import backups
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool


def register_routes(app, context):
    settings, store, worker = context.settings, context.store, context.worker
    translation_worker, get_job = context.translation_worker, context.get_job

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
