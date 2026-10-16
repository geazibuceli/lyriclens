import json
import sqlite3
import threading
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "jobs.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def put(self, job):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?)", (job["id"], json.dumps(job, ensure_ascii=False)))

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, job_id, **changes):
        with self.lock:
            job = self.get(job_id)
            job.update(changes)
            self.put(job)
            return job

    def list(self):
        with self.connect() as db:
            return sorted([json.loads(r[0]) for r in db.execute("SELECT body FROM jobs")], key=lambda j: j["created_at"], reverse=True)

    def recover(self):
        for job in self.list():
            if job["state"] in ("queued", "processing"):
                self.update(job["id"], state="interrupted", stage="Interrupted by service restart", completed_at=now())

    def delete(self, job_id):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
