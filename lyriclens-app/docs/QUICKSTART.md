# Start using LyricLens

## First setup on Windows

Open a terminal in the repository folder and run:

```powershell
.\setup.cmd -InstallPrerequisites
.\start.cmd
```

Setup installs Python 3.11 and Node.js through Windows Package Manager if needed, prepares the application environment, installs bundled FFmpeg and downloads Whisper Small (about 500 MB). Windows may ask for installation permission. Internet access is needed for this first setup.

Open **http://127.0.0.1:5181/**. On later visits, run only `.\start.cmd`.

If Python 3.11 and Node.js 22+ are already installed, use `.\setup.cmd`. Check an installation without changing it with `.\setup.cmd -CheckOnly`. For manual installation, macOS/Linux, Docker or GPU configuration, see [Setup](SETUP.md).

## Transcribe a recording

1. Choose an audio or video file.
2. Select its language, or leave automatic detection selected.
3. Click **Transcribe clip**.
4. Listen to the result, correct the text and click **Save edits**.
5. Open **Export** for TXT, SRT, JSON or synchronized LRC lyrics.

Supported formats: WAV, MP3, FLAC, M4A and MP4. Default limits are 10 minutes and 150 MiB. MP4 uses the first audio track.

**Advanced transcription options** contains the recognition model and vocal isolation controls. Use **Compare both pipelines** to review original audio and isolated vocals side by side. These options may need additional models or dependencies; the interface shows preparation status.

## Review and translate

For multiple recordings, open **Transcribe multiple recordings** below the upload controls. Select up to 20 files and click **Send pending recordings**. Each file uses the selected language, model and listening mode and gets its own library entry. Uploads pause on a failed request; after freeing queue space, continue sending pending recordings. Already accepted files are skipped. **Stop after current upload** stops further uploads; cancel accepted jobs individually in the library. The pending file list lasts only while the upload page stays open. After a connection error, check the library before retrying to avoid duplicating an upload whose response was lost.

Search the library by title or filename, filter by state or requested language, and open **Rename recording** to set a saved display title. In the editor, **Import lyrics (TXT / LRC)** can preserve passage times, read LRC timestamps or distribute lines for manual timing adjustments. See [Editing](EDITING.md) for limits and behavior.

Click a segment timestamp to seek, or **Repeat** to listen to it in a loop. Playback speed helps with difficult passages. Save edits before exporting or translating.

For translation, open **Translate transcript** under a completed result. [Translation setup](TRANSLATION.md) prepares the optional local translation model. For mixed-language songs, see [Multilingual review](MULTILINGUAL.md).

## If something goes wrong

- **The page does not open:** run `.\start.cmd` and check the log path it prints.
- **Transcription is unavailable:** run `.\setup.cmd -CheckOnly`; setup needs dependencies and prepared model weights.
- **Words are wrong:** select the language manually, compare vocal isolation and review against the audio.

More solutions are in [Troubleshooting](TROUBLESHOOTING.md). Recordings and saved transcripts are stored locally in `lyriclens-app/data`; job backups are available in **Backup and restore a job**.
