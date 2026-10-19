# Reviewed-data Whisper Small fine-tuning

Fine-tune the Whisper Small decoder using reviewed recordings, a frozen encoder, float32 and gradient accumulation. Training runs in a separate environment. Compare candidate models against the baseline before installing one in the app.

## Current prerequisites

Training requires a CUDA-enabled PyTorch build in a separate Python 3.11 environment. The local RTX 5080 has 16303 MiB VRAM; measure memory use with your chosen data and batch settings. The application uses CPU PyTorch for separation and CTranslate2 for GPU recognition.

The current review queue contains 12 development clips in six languages, all pending human reference review. Add Japanese examples and a separate final set, and complete training-permission review before using these recordings.

The prepared `.venv-training` environment uses PyTorch `2.8.0+cu128` and passed CUDA forward/backward and tiny-Whisper gradient checks. The Small base is cached at `.runtime/whisper-small-training-base`, revision `973afd24965f72e36ca33b3055d56a652f456b4d`. Singing fine-tuning is pending reviewed training data.

## Environment

From the repository root, create an isolated environment and install a pinned CUDA-enabled PyTorch build. The following commands target the documented Blackwell-compatible CUDA 12.8 build; do not run them in the application's environment:

```powershell
.\.venv311\Scripts\python.exe -m venv .venv-training
.\.venv\Scripts\uv.exe pip install --python .venv-training/Scripts/python.exe torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\uv.exe pip install --python .venv-training/Scripts/python.exe -e './lyriclens-app/backend[training,tools,test]'
.\.venv-training\Scripts\python.exe -m lyriclens.finetune hardware
```

The hardware command runs a small CUDA forward/backward probe. Stop heavy inference jobs before training. To train on CPU, pass `--device cpu`.

## Data and human review

Training uses original contributor recordings with documented permission. See the [training sources guide](TRAINING_SOURCES.md) for selection criteria, licensing and evidence requirements.

Use [BENCHMARK.md](BENCHMARK.md) to review references. Before verification, set `training_allowed: true` and document permission for the audio, reference text and adaptation in `training_permission`. Changes to either field require a new review.

Each training/validation example must be manually aligned, single-language, nonempty sung text and at most 30 seconds. The first trainer rejects mixed-language clips and longer recordings instead of truncating them. Review shorter aligned excerpts separately. Include diverse singers, songs, accompaniment and difficult phonetic examples rather than only one song or its repeated choruses. A reference can come from authorized dataset annotation, but must still be checked against the audio.

Use development clips only for train/validation. Create `.runtime/training-assignment.json` with explicit clip IDs:

```json
{"train":["TRAIN_CLIP_ID"],"validation":["OTHER_SONG_CLIP_ID"]}
```

Keep training and validation groups and audio hashes separate. Reserve final clips for final evaluation. The review gate checks the manifest, hashes and review fingerprints.

An intentionally empty template is in [training-assignment.example.json](../evaluation/training-assignment.example.json). Populate IDs only after reviewing group relationships and permissions.

## Freeze the base and plan

Use the original Hugging Face `openai/whisper-small` trainable checkpoint, not the application's converted CTranslate2 binary. Resolve and record an exact 40-character commit SHA from the official model repository. Use that same SHA below; moving branches such as `main` are rejected:

```powershell
# The base preparation below has already been performed on this machine.
.\.venv-training\Scripts\python.exe -m lyriclens.finetune prepare-base .runtime/whisper-small-training-base --revision 973afd24965f72e36ca33b3055d56a652f456b4d
.\.venv-training\Scripts\python.exe -m lyriclens.finetune plan .runtime/reviewed-v1.jsonl .runtime/training-assignment.json .runtime/training-plan-v1.json --base-revision 973afd24965f72e36ca33b3055d56a652f456b4d --epochs 3
```

`prepare-base` downloads the Small weights, tokenizer and configuration. Planning records the manifest hash, assignments, hyperparameters, seed, base revision, language coverage and duration. Training checks the plan and manifest before starting.

## Train and inspect validation

```powershell
.\.venv-training\Scripts\python.exe -m lyriclens.finetune train .runtime/training-plan-v1.json .runtime/whisper-small-training-base .runtime/training-run-v1 --device cuda
```

This runs offline from local safetensors. Audio is decoded with FFmpeg and checked against reviewed duration; input features are cached temporarily on disk, and overlong decoder targets fail rather than being truncated. Each example gets its own language/transcription prefix. Training saves full HF checkpoints with safetensors after each epoch and generates validation hypotheses with CER/WER using the project's unchanged normalization. Empty/unsupported cases retain the evaluator's semantics.

Each epoch is saved for comparison. `history.json` contains validation text and metrics; keep it private when required by the data permissions. The run also records the environment, hardware, plan and a `COMPLETE.json` or `FAILED.json` status. Use a new output directory for each run. Optimizer resume and automatic out-of-memory recovery are unavailable.

## Convert and compare

Choose an epoch using validation only:

```powershell
.\.venv-training\Scripts\python.exe -m lyriclens.finetune convert .runtime/training-run-v1/epoch-1 .runtime/whisper-small-candidate-v1
.\.venv311\Scripts\python.exe -m lyriclens.evaluate .runtime/reviewed-v1.jsonl --require-reviewed --split development --candidate .runtime/whisper-small-candidate-v1 --device cuda --compute float16 --output .runtime/candidate-development-v1.json
```

Install CTranslate2 in the training environment with `uv pip install --python .venv-training/Scripts/python.exe ctranslate2==4.8.3`. Conversion writes a local candidate directory with the model, tokenizer, feature extractor and binary hash. Evaluate it against the baseline using the same clips and settings, then compare with `lyriclens.benchmark compare`. Report training/validation results separately from results on unseen recordings.

Choose a candidate using development results, then evaluate once on a separate reviewed final manifest with `--split final`. Report coverage and failures for each intended language. Review those results before installing the candidate in the app.

Implementation references: [Transformers 4.49 Whisper](https://huggingface.co/docs/transformers/v4.49.0/en/model_doc/whisper), [CTranslate2 Transformers conversion](https://opennmt.net/CTranslate2/guides/transformers.html), [official PyTorch Blackwell/CUDA 12.8 announcement](https://pytorch.org/blog/pytorch-2-7/), [PyTorch pinned installation commands](https://pytorch.org/get-started/previous-versions/).
