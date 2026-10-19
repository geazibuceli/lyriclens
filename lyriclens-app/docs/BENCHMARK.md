# Human-reviewed singing benchmark

This local CLI workflow prepares reference review, freezes an evaluation protocol and compares model runs. It does not generate reference lyrics, certify a reviewer, train models or establish a new accuracy result. A human fluent in each language must listen and check references and permissions. Existing diagnostic reports remain separate.

Run commands from the repository root with the installed Python 3.11 environment. All paths below are local and ignored by Git. Keep restricted audio, reference text, reviewer identities and full evaluation outputs private.

## Prepare the review queue

Start with a JSONL manifest described in [EVALUATION.md](EVALUATION.md). Required fields include audio path/hash, language, duration, reference, reference source, permissions, conditions, language switching and development/final split. Missing annotations must be completed before approval; an empty reference means genuinely no sung words, not an unknown lyric.

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark prepare .runtime/singing-research/manifest.jsonl .runtime/singing-review.json
.\.venv311\Scripts\python.exe -m lyriclens.benchmark status .runtime/singing-review.json
```

Every imported reference starts **pending**, including dataset-supplied annotations. No ASR output is imported as a reference. The queue contains absolute audio paths and editable reference metadata. Preparation refuses to overwrite an existing queue.

The existing research manifest has 12 development clips spanning six languages, with restricted sources retained locally. It has no Japanese example and no untouched final set. This queue is a starting point, not a representative seven-language benchmark. Add appropriately authorized independent recordings covering all seven languages, accompaniment, overlapping voices, effects, noise and language switching. Keep previously inspected recordings in development.

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

This records an explicit attestation, time and annotation fingerprint. It cannot prove that the operator listened. The assistant must not issue it on a person's behalf or invent a reviewer. Any change to reference, language, split, group, path, hash or other annotation invalidates the attestation. Audio content changes are also rejected. Keep pending additions in a separate queue if they should not block an already curated dataset version.

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark export .runtime/singing-review.json .runtime/reviewed-v1.jsonl
```

Export requires every included clip to be reviewed, validates audio hashes, rejects split leakage and reports seven-language coverage, including zeros. It refuses to replace an existing manifest. Fingerprints detect accidental changes; they are not cryptographic proof of human review or permission.

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

Different clip sets, audio hashes, references, language labels, conditions, splits or missing pipeline rows are rejected. A comparison is evidence on that sample, not proof of statistical significance or universal improvement.

## Final evaluation

Choose one model and one language mode using development results, then freeze a new final protocol:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.benchmark plan .runtime/reviewed-v1.jsonl .runtime/final-v1.json --split final --profiles large-v3 --language-modes auto --device cpu --compute int8
.\.venv311\Scripts\python.exe -m lyriclens.benchmark run .runtime/final-v1.json
```

Final protocols reject a tuning matrix. Inspect the frozen protocol before execution and run final once. The filesystem guard prevents overwriting that run, but cannot prevent someone from creating a different protocol or deleting files. After inspecting final outcomes, further tuning requires a new untouched final set.

The existing evaluator also accepts `--require-reviewed` for direct invocations. Legacy diagnostics remain runnable without this flag and must not be represented as the reviewed benchmark. Fine-tuning and a claim of reduced singing error remain future work requiring sufficient reviewed/licensed data, hardware and independent final evaluation.
