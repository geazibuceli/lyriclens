"""Services shared by HTTP route groups."""
from dataclasses import dataclass
from fastapi import HTTPException
from .config import Settings
from .store import Store
from .worker import Worker
from .translation import TranslationWorker


@dataclass
class ApiContext:
    settings: Settings
    store: Store
    worker: Worker
    translation_worker: TranslationWorker

    def get_job(self, job_id):
        job = self.store.get(job_id)
        if job is None:
            raise HTTPException(404, 'Job not found')
        return job
