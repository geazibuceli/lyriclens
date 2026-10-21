# Human-reviewed singing benchmark

Use the [quality plan](QUALITY.md) to collect representative recordings and audit language, condition and split coverage before freezing a protocol.

For representative comparisons, add `--representative` to `plan`. This requires reviewed original groups for all seven languages and recording conditions in both splits. The minimum defaults to two independent groups and is saved in the protocol. Leave the flag off for small development diagnostics.

Prepare reviewed references, freeze an evaluation protocol and compare model runs. A fluent reviewer checks each recording, its reference text and the relevant permissions.

Run commands from the repository root with the installed Python 3.11 environment. All paths below are local and ignored by Git. Keep restricted audio, reference text, reviewer identities and full evaluation outputs private.

## Prepare the review queue

Start with a JSONL manifest described in [EVALUATION.md](EVALUATION.md). Required fields include audio path/hash, language, duration, reference, reference source, permissions, conditions, language switching and development/final split. Missing annotations must be completed before approval; an empty reference means genuinely no sung words, not an unknown lyric.

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark prepare .runtime/singing-research/manifest.jsonl .runtime/singing-review.json
.\.venv311\Scripts\python.exe -m lyriclens.benchmark status .runtime/singing-review.json
```

Every imported reference starts **pending**, including dataset-supplied annotations. No ASR output is imported as a reference. The queue contains absolute audio paths and editable reference metadata. Preparation refuses to overwrite an existing queue.

The current manifest contains 12 development clips in six languages. Add Japanese recordings and an independent final set, with varied singers, accompaniment, overlapping voices, effects, noise and language switching. Keep previously inspected recordings in development.

## Human review

Open the queue JSON in your editor and listen to the exact recording in your audio player. For each clip:

1. Correct `reference` from listening and an authorized reference source. Retain repeated lines, accents and script distinctions. Do not translate or fill uncertain words from model output.
2. Confirm language, duration, conditions, language-switching flag and audio/text permissions. Leave uncertain examples pending.
3. Fill `group_id` with a consistent song/recording/singer-session group. All excerpts or related performances that could leak information must share a group. Grouping cannot be inferred reliably from file names; it needs human curation.
4. Choose `development` or `final`. Related groups and identical audio cannot span both. Do not move material already used for tuning into final.
5. After listening and checking text permissions, the **human reviewer** runs:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark verify .runtime/singing-review.json CLIP_ID --reviewer "YOUR_REVIEWER_ID" --confirm-listened-and-text-permission
```

Verification records the reviewer, time and annotation fingerprint. The reviewer must listen to the recording and check text permissions before running this command. Changes to annotations or audio require a new review. Keep pending additions in a separate queue when extending a reviewed dataset.

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark export .runtime/singing-review.json .runtime/reviewed-v1.jsonl
```

Export checks review status, audio hashes and split isolation, then reports coverage for all seven languages. Choose a new filename for each manifest version.

## Freeze and run development comparisons

Prepare the existing Small, Large-v3 and separation models explicitly using [SETUP.md](SETUP.md). Nothing here downloads models. Stop other heavy jobs for comparable timings.

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark plan .runtime/reviewed-v1.jsonl .runtime/development-v1.json --split development --profiles configured large-v3 --language-modes auto manual --device cpu --compute int8
.\.venv311\Scripts\python.exe -m lyriclens.benchmark run .runtime/development-v1.json
```

Each matrix entry runs in a separate process and evaluates both direct and isolated-vocal recognition on the same originals. For a prepared CUDA environment use `--device cuda --compute float16` when planning. Protocols freeze manifest hash, model IDs/revisions, inference settings, language modes and separation device. Changed manifests/configurations are rejected before inference. Each protocol gets a new `.runs` directory; an existing directory blocks reruns or overwrites.

The directory contains full per-clip results, per-language micro CER/WER, failures, timing/environment data, process exit status and paired comparisons against the first matrix entry. Negative CER deltas favor the candidate. Failed pairs remain visible with null deltas. Read failures and per-condition examples, not only aggregate numbers. Japanese/Mandarin WER stays null; no validated tokenizer is configured. Mixed-language clips do not establish per-language detection accuracy or a validated automatic code-switch benchmark.

You can compare existing compatible reports explicitly:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark compare BASELINE.json CANDIDATE.json .runtime/comparison-v1.json
```

Reports must use the same clips, hashes, references, language labels, conditions, splits and pipeline rows. Interpret improvements within that sample; statistical significance needs a separate analysis.

## Four-way quality and timing summary

After evaluating the same manifest with Small and Large-v3, summarize both original-audio and separated-vocal routes together:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark summarize SMALL_REPORT.json LARGE_REPORT.json .runtime/four-way-summary.json
```

Pass the Small report first and Large-v3 second, using the same language mode. For example, reviewed protocol outputs can be `development-v1.runs/configured-manual.json` and `development-v1.runs/large-v3-manual.json`. The summary refuses to overwrite an existing output. It contains aggregate metrics and model configuration, without lyrics, hypotheses, raw responses, clip IDs or audio paths.

All four combinations use **the same successful clips** for accuracy and timing, overall and per language. Micro CER/WER uses summed error counts divided by summed reference counts, rather than an average of clip percentages. Attempted, completed and failed counts still cover every clip. Missing languages and unavailable metrics remain explicit. Empty-reference insertion counts remain visible because CER has no nonzero reference denominator for instrumental recordings. Do not interpret fewer failures as proof of better lyric recognition.

New evaluator reports record `stage_seconds` for decode, separation (including its output decode) and recognition. Recognition includes initial model loading when needed; separation includes initial worker loading when needed. End-to-end time also includes validation and local bookkeeping. Times are diagnostic measurements with model reuse, rather than steady-state latency estimates. Old reports remain supported but unavailable stage timings are omitted. Sampled RSS excludes GPU memory.

Unreviewed diagnostics carry `human_review_required: false` in the summary. Complete reference review and evaluate an independent final set before changing model defaults.

Recognition without alignment now permits one same-checkpoint native-alignment retry for invalid timing. Evaluator rows record `timing_recovery` and private raw reports retain both attempts. Recognition time includes the retry when one occurs. `benchmark compare` includes per-pair attempted/succeeded recovery flags, and keeps CER deltas null for formerly failed pairs. See [the recovery rerun](SINGING.md#automatic-timing-recovery-rerun) for current evidence; historical reports remain unchanged.

To rerun the local unreviewed development comparison without replacing earlier reports, create a new output directory, then run:

```powershell
New-Item -ItemType Directory .runtime/singing-comparison-v2
.\.venv311\Scripts\python.exe -m lyriclens.evaluate .runtime/singing-research/manifest.jsonl --split development --manual-language --model-profile configured --device cuda --compute float16 --output .runtime/singing-comparison-v2/small.json
.\.venv311\Scripts\python.exe -m lyriclens.evaluate .runtime/singing-research/manifest.jsonl --split development --manual-language --model-profile large-v3 --device cuda --compute float16 --output .runtime/singing-comparison-v2/large-v3.json
.\.venv311\Scripts\python.exe -m lyriclens.benchmark summarize .runtime/singing-comparison-v2/small.json .runtime/singing-comparison-v2/large-v3.json .runtime/singing-comparison-v2/summary.json
```

These commands require the local research manifest and explicitly prepared models; they download nothing. For CPU, use `--device cpu --compute int8` in both evaluations. Use the reviewed protocol workflow above for curated evaluation.

## Final evaluation

Choose one model and one language mode using development results, then freeze a new final protocol:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark plan .runtime/reviewed-v1.jsonl .runtime/final-v1.json --split final --profiles large-v3 --language-modes auto --device cpu --compute int8
.\.venv311\Scripts\python.exe -m lyriclens.benchmark run .runtime/final-v1.json
```

Final protocols accept one model and language mode. Inspect the protocol, run final evaluation once and keep the output. Further tuning needs a new untouched final set.

For direct evaluator calls, pass `--require-reviewed` to enforce reference review. Use legacy diagnostic runs for development and the reviewed protocol for final comparisons.
