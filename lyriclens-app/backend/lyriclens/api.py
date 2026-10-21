import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import Settings
from . import translation as mt
from .store import Store
from .worker import Worker
from .limits import UploadLimit
from .context import ApiContext
from .routes import translation, environment, archives, jobs, recognition, exports


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

    context = ApiContext(settings, store, worker, translation_worker)
    translation.register_routes(app, context)
    environment.register_routes(app, context)
    archives.register_routes(app, context)
    jobs.register_routes(app, context)
    recognition.register_routes(app, context)
    exports.register_routes(app, context)
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
