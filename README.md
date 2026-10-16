# LyricLens

Turn music into editable transcripts, locally. Upload a recording, compare recognition with and without vocal separation, review timestamps, and export the result.

![LyricLens upload workspace with language, listening mode and recognition model controls](lyriclens-app/docs/images/workspace.png)

## Features

- **Seven language choices:** Korean, Japanese, Mandarin Chinese, English, Spanish, Portuguese and French, plus automatic whole-clip detection.
- **Local recognition:** Whisper Small or experimental Large-v3, with optional Demucs vocal separation and side-by-side results.
- **Review and export:** audio playback, approximate segment timestamps, Unicode editing, passage retranscription, and TXT, JSON or SRT export.
- **Persistent history:** saved jobs, cancellation and deletion. Audio stays local; the app does not look up songs or retrieve lyrics.

**Formats:** WAV, MP3, FLAC, M4A and MP4. Default limits: **10 minutes of audio** and **150 MiB per upload**. MP4 processing uses the first audio track and ignores video frames.

## Quick start

Install **Python 3.11**, **Node.js** and **FFmpeg**. From the repository root, in PowerShell:

```powershell
cd lyriclens-app
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[inference,tools]'
.\.venv\Scripts\python.exe -m lyriclens.models download
.\.venv\Scripts\python.exe -m uvicorn lyriclens.api:app --host 127.0.0.1 --port 8011
```

In another terminal, starting at the repository root:

```powershell
cd lyriclens-app/frontend
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:5181**. Model preparation requires an explicit download; transcription runs locally afterward. This setup enables Small with direct recognition. For Large-v3, vocal separation, GPU setup, Docker or Bash commands, see the [setup guide](lyriclens-app/docs/SETUP.md).

## Limitations

Singing, accompaniment and overlapping voices can produce incorrect words or hallucinations; timestamps are approximate. Review every transcript. Existing singing results come from small development samples, and Japanese accuracy remains unscored. See the [singing results](lyriclens-app/docs/SINGING.md).

## Documentation

| Guide | Contents |
|---|---|
| [Setup and operations](lyriclens-app/docs/SETUP.md) | Installation, model preparation, GPU, Docker and test commands |
| [Architecture](lyriclens-app/docs/ARCHITECTURE.md) | Backend, frontend, job processing and API |
| [Models](lyriclens-app/docs/MODELS.md) | Profiles, dependencies and third-party attribution |
| [Evaluation](lyriclens-app/docs/EVALUATION.md) | Metrics, references and evaluation protocol |
| [Verification](lyriclens-app/docs/VERIFICATION.md) | Executed checks and remaining limitations |
| [Troubleshooting](lyriclens-app/docs/TROUBLESHOOTING.md) | Common setup and runtime problems |

## License

[MIT](lyriclens-app/LICENSE) for project source. Models, dependencies and datasets have separate licenses documented with their sources. Model weights and downloaded research audio are not included.
