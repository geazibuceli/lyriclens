# Drafts, segment editing, bilingual exports and job backups

## Browser drafts

Transcript and translation text changes are stored automatically in this browser profile after a 300 ms pause. A best-effort flush also runs when leaving the page. After reloading or reopening a job, choose **Restore browser draft** or **Discard browser draft**. Restoring changes the editor only. **Save edits** or **Save translation edits** still updates the server, exports and backups.

Drafts are separate for each job, recognition route and translation target. A changed saved baseline produces a conflict notice; there is no automatic merge or overwrite of the server record. Stale translations must be regenerated before restoring an old translation draft. Drafts do not include undo history. They are local to the browser/origin, not synchronized across devices or tabs, not encrypted, and not included in backups. Browser storage cleanup/private mode, quota limits and a hard crash before the debounce/flush can lose a draft. Storage failures are shown explicitly; saving to the job remains available. Each stored draft is capped at two million serialized characters, and the browser's overall quota can be smaller than the sum of drafts.

## Search and segment boundaries

Each route has **Search transcript**, which searches saved or unsaved text using Unicode NFC and case-insensitive matching while retaining accents. Matching buttons scroll to the segment and seek the original audio. Search does not change text or locate exact word times.

Open **Split or merge segment N**. Choose an interior split time and a text cut separately. The preview shows the cut; no forced alignment is inferred. Text positions count Unicode code points, preserving surrogate pairs but not guaranteeing complete grapheme clusters. Both new segments inherit the original language and can then be relabeled. There is a maximum of 1000 segments.

**Merge segment N with next** requires ordered, nonoverlapping segments with the same language. It spans the first start to the next end, includes any intervening gap and joins the texts with a newline. Different-language segments must remain separate or be relabeled explicitly first. Merged text is limited to 20000 characters. Split/merge changes participate in undo/redo and browser drafts; save them before retranscription, translation or export. Neither operation rewrites the original recognition output.

## Bilingual exports

After saving a current translation, open **Export translation** and choose **Bilingual TXT** or **Bilingual SRT**. Each block contains the saved source snapshot followed by its generated or edited translation. SRT retains source segment times. Source changes, including language labels or split/merge, make older translations stale; regenerate before bilingual export. This is a two-line/block comprehension export, not a singable translation.

API: `GET /api/jobs/{id}/export?pipeline=direct&translation=pt&bilingual=true&format=srt`. Bilingual mode supports TXT and SRT; missing translations, stale source or unavailable alignment are rejected.

## Backup and restore

Open **Backup and restore a job**. Stop active work and save edits, then download the selected job's `.lyriclens.zip` archive. It includes the byte-identical original recording, saved original/edited results, translations, raw responses where present, model identifiers/revisions and job configuration. It excludes model weights, decoded audio/stems, browser drafts, environments and the entire library database. Back up each job separately. Archives can contain private recordings and text and are not encrypted.

Choose the archive under **Job backup ZIP**, then **Restore as a separate job**. The importer checks format/version, allowed members, metadata, recording size/SHA-256, segment timing and translation alignment. It rejects duplicate/linked members, arbitrary paths, encrypted ZIPs and oversized content. Entries are copied by known names; archive paths are never extracted. Existing jobs are not replaced and imported active states become interrupted. No model download or recognition starts during restoration.

Imported ASR snapshots cannot resume recognition automatically from supplied model settings. Upload the restored original as a new recognition job if needed; saved transcript/translation editing and exports remain available. A valid stopped translation checkpoint can resume against its preserved source with the explicitly prepared local translation model.

Original recording size and duration must fit the configured application limits (default 150 MiB / 600 seconds). Job metadata and each optional raw response are limited to 32 MiB; the restore body limit adds bounded archive/multipart overhead. Backups created from another installation with larger limits may be rejected. Raw responses are retained as diagnostic data, not executed. Keep the source archive until the restored job is checked.

API: `GET /api/jobs/{id}/backup` downloads one stopped job; `POST /api/backups/restore` accepts a multipart `file` and creates a new UUID. Models must be prepared separately after moving to another machine.

## Continuous checks

The GitHub workflow checks backend tests, frontend formatting and the production build. A separate Chromium job installs only test/browser/FFmpeg tools and runs owned-silence editing, recovery UI, waveform, storage and playback checks with temporary app data. No recognition or translation model is downloaded by this job. Logs/screenshots are uploaded as diagnostics on failure or success. Real-model quality evaluations remain explicit and separate.

Run the same isolated browser workflow locally with installed dependencies and Playwright Chromium:

```powershell
.\.venv\Scripts\python.exe lyriclens-app/scripts/ci_browser.py --backend-port 8013 --frontend-port 5183
```

Default CI ports are 8011/5181. Occupied ports are rejected without stopping existing services; the runner terminates only processes it created. The smoke scripts support `LYRICLENS_BROWSER_URL` for isolated test servers. Local Chromium runs passed desktop/mobile layouts and axe WCAG A/AA checks. These checks do not establish singing accuracy or replace assistive-technology review.
