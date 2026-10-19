# Local transcript translation

Translate a reviewed transcript locally, then edit and export the translation alongside the saved source. Translation aims to convey meaning; rhyme and rhythm may change.

## Setup

From `lyriclens-app`, using the Python 3.11 environment described in [SETUP.md](SETUP.md):

```powershell
.\.venv\Scripts\python.exe -m pip install -e './backend[translation]'
.\.venv\Scripts\python.exe -m lyriclens.models translation-download
```

Restart the backend after installing optional dependencies. In the prepared IDE workspace, run these commands from the repository root with `.\.venv311\Scripts\python.exe`, installing `./lyriclens-app/backend[translation]` instead. Reload the page after preparation.

Preparation explicitly downloads the official [Meta M2M100 418M checkpoint](https://huggingface.co/facebook/m2m100_418M/tree/55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636), revision `55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`, and converts it to CTranslate2 int8. Source weights and the converted checkpoint stay under ignored `lyriclens-app/data/translation-models`. Conversion retains the tokenizer locally. Runtime loading uses local files only; neither the readiness endpoint nor a translation request downloads weights. The model card declares MIT and lists all seven target language codes. Published language support is not a lyric-quality guarantee.

Translation runs on CPU/int8, independently of the ASR device. The pinned optional extra uses CTranslate2 4.8.3, Transformers 4.49.0, SentencePiece 0.2.1 and PyTorch 2.5.1. The conversion adapter maps CTranslate2's newer `dtype` argument to `torch_dtype` for the pinned Transformers release. The retained source checkpoint adds disk use beyond the converted model; it is not removed automatically.

## Use

1. Complete transcription and save any corrections.
2. Open **Translate transcript** under either recognition result.
3. Confirm **Translation source language**, select **Translation target language**, and click **Translate saved text**.
4. Review source and translated text side by side. Edit the translation and click **Save translation edits**.
5. Use **Export translation** for separate TXT, JSON or SRT output. The original transcript's export remains independent.

Korean, Japanese, Mandarin Chinese, English, Spanish, Portuguese and French can each be chosen as source or target. Source language is a user instruction: the whole-clip ASR estimate is only an initial suggestion. Saved segment language labels take priority over the source selector, which provides the fallback for unlabeled segments. Mixed-language transcripts can be translated in one request; segments already in the target language are copied unchanged. A request is rejected if every nonempty source segment is already in the target language. The translator does not detect segment languages automatically. See the [multilingual review guide](MULTILINGUAL.md).

Translated segments inherit their source timestamps exactly; these remain approximate ASR/user times, not translation-specific speech alignment. The source snapshot, its hash, source version (original or edited), source/target language, model revision, CPU/int8 settings and translation output are persisted. Translation edits preserve the generated version. JSON export includes this provenance.

Editing source text or its timing marks existing translations stale. Stale translations remain visible, but editing/export is blocked until the current source is translated again. Unsaved source or translation edits also block their relevant UI actions. Translating again explicitly replaces that target-language translation for the selected recognition route.

## Processing and limits

A dedicated single translation thread reuses one lazy-loaded model and has a bounded queue using the configured queue size. Audio processing remains independent. Progress is recorded per segment. Cancellation is cooperative between segments and checked after an active segment returns. A translation with pending cancellation remains active until acknowledged; job deletion is blocked while translation is active. Service restart marks unfinished translations interrupted.

At most 1000 source segments and 100000 source characters are accepted per request. Each segment is limited to 512 input tokens and 512 generated tokens, using beam size 4. Text is never silently truncated: oversized or incomplete generation fails with a message to shorten/split the source. Empty segments remain empty. Long segments can be split using the transcript editor before translation. Segments are translated separately, so context across lines can be lost and poetic or ambiguous language may be mistranslated.

Review translations against the source: recognition errors and ambiguous lyrics can affect the wording. Translation quality on lyrics has not been benchmarked. A failed translation leaves the transcript available.

## API

Translation fields also support explicit restoration of browser drafts and bilingual TXT/SRT exports combining the saved source and current translation. See [EDITING.md](EDITING.md) for behavior and limits.

| Endpoint | Purpose |
|---|---|
| `GET /api/translation` | Model preparation, dependency readiness and language choices; no inference/download |
| `POST /api/jobs/{id}/translate` | Queue translation with `pipeline`, `source_language`, `target_language` |
| `POST /api/jobs/{id}/translation/cancel` | Request cancellation for that pipeline/target |
| `PUT /api/jobs/{id}/translation` | Save `texts` in source segment order, with `pipeline` and `target_language` |
| `GET /api/jobs/{id}/export?pipeline=direct&translation=pt&format=srt` | Export one completed, current translation |

Jobs expose translations in `translations`, keyed by `pipeline:target_language`. `original=true` on a translation export selects its generated version instead of translation edits; it does not change the original transcript. Busy/stale/unprepared requests return 409; invalid languages/empty source return 422; a full translation queue returns 429. A failed queue submission restores any previous translation.

## Verification

Integration tests inject a deterministic translator to verify all 42 cross-language request routes, saved-source snapshots, Unicode edits, independent exports, inherited timing, stale-source guards, queue rollback, failure isolation, cancellation, deletion guards and restart recovery. These tests do not measure model quality.

The local checkpoint completed **42/42** smoke-test executions on short non-lyrical sentences. [translation-smoke.json](../evaluation/translation-smoke.json) records inputs, outputs, settings, environment and timings. Lyric translation quality still needs evaluation. Reproduce from the repository root:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/translation_smoke.py
# With both native servers running and Playwright/axe installed:
.\.venv\Scripts\python.exe lyriclens-app/scripts/translation_browser_smoke.py
```

The browser test uses a temporary silence recording and sample text. Reports and screenshots are saved under ignored `artifacts/browser-translation`.

## Docker

Optional packaging is available with `docker compose build --build-arg WITH_TRANSLATION=true backend`, followed by `docker compose run --rm backend python -m lyriclens.models translation-download`. To also include separation, pass both `WITH_TRANSLATION=true` and `WITH_SEPARATION=true`. This translation-specific Docker profile has not been executed in the native Windows verification; earlier Docker checks concern ASR/separation. Restart/recreate the backend after building and preparing the model.

Official implementation references: [M2M100 model card](https://huggingface.co/facebook/m2m100_418M), [CTranslate2 M2M100 conversion and target-prefix example](https://opennmt.net/CTranslate2/guides/transformers.html#m2m-100).
