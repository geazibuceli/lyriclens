# Developer guide

## Code layout

The frontend entry point is `frontend/src/main.tsx`. `app.tsx` coordinates the library and selected job. Features are split into `upload-form.tsx`, `transcript-editor.tsx`, `region-retry.tsx`, translation, playback and workspace tools. Shared API requests and types live in `api.ts` and `types.ts`.

The backend entry point is `backend/lyriclens/api.py`. It constructs services, middleware and the application lifecycle. `context.py` provides shared services to route groups under `routes/`:

| Module | Responsibility |
|---|---|
| `jobs.py` | Upload, library, edits, cancellation, resume and deletion |
| `recognition.py` | Passage and multilingual retranscription |
| `translation.py` | Translation lifecycle and saved edits |
| `environment.py` | Readiness, diagnostics, waveform and storage |
| `archives.py` | Job backup and restore |
| `exports.py` | Transcript/translation exports and raw responses |

Recognition runs in `worker.py` through the adapters in `adapters.py`. Model preparation, evaluation and training remain separate CLI tools.

## Local checks

From the repository root, with the development dependencies installed:

```powershell
.\.venv311\Scripts\python.exe -m pytest lyriclens-app/backend/tests -q
npm.cmd --prefix lyriclens-app/frontend run format:check
npm.cmd --prefix lyriclens-app/frontend run test:studio
npm.cmd --prefix lyriclens-app/frontend run build
```

The initial setup installs runtime dependencies. Add tests with `python -m pip install -e './lyriclens-app/backend[test]'` using the same environment.

Browser checks use isolated data and ports; install the `browser` extra and Playwright Chromium first:

```powershell
python lyriclens-app/scripts/ci_browser.py --backend-port 8013 --frontend-port 5183
```

The runner covers simple upload, editing, recovery, playback, mobile layouts and accessibility. It creates and removes its own fixtures and stops only its own processes. `--scripts onboarding_browser_smoke.py` runs the upload check alone. Screenshot and log artifacts go under ignored `lyriclens-app/artifacts`.

The default browser run also checks the listening studio and recognition controls
using deterministic API fixtures, without downloading or loading recognition
models. To run those checks alone:

```powershell
python lyriclens-app/scripts/ci_browser.py --backend-port 8013 --frontend-port 5183 --scripts studio_browser_smoke.py recognition_settings_browser_smoke.py
```

The CI runner sets `LYRICLENS_STUDIO_MEDIA_DIR` to its artifact directory so
studio checks do not overwrite committed README images and video. Running
`studio_browser_smoke.py` directly still regenerates documentation media by
default; set that variable to choose a different output directory.

GitHub Actions runs backend pytest, frontend formatting, lyric-timing tests,
the production build and all default browser checks. Recognition accuracy on
real music remains a separate reviewed benchmark, rather than a model download
or inference requirement for every pull request.

The Docker CI matrix also builds and starts both services with CPU vocal
separation enabled and disabled. It checks optional imports in the enabled
image and runs `scripts/docker_smoke.py` through Nginx. Logs and reports are
uploaded as Docker diagnostics. Only the isolated CI project's containers and
temporary volume are removed; local application data is not used by that job.

## Recognition changes

Use [the quality plan](QUALITY.md) and [reviewed benchmark](BENCHMARK.md) when changing recognition settings. Keep source permissions, reference review, model revision and input hashes with the evaluation. Unit and browser tests validate software behavior; record model quality separately by language and recording condition.
