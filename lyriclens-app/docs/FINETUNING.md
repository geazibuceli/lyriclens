# Reviewed-data Whisper Small fine-tuning

This is a separate experimental training workflow, not a trained replacement for the app. It trains the Whisper Small decoder with a frozen encoder, float32, one clip per batch and gradient accumulation. Existing inference checkpoints and application dependencies are untouched. A lower training loss is not evidence of better singing recognition.

## Current prerequisites

The local machine reports an RTX 5080 with 16303 MiB VRAM. The application's PyTorch is `2.5.1+cpu`: CTranslate2 GPU recognition does not establish PyTorch training readiness. Use a separate Python 3.11 environment for training. The actual model/batch memory requirement must be measured; neither GPU model nor free memory guarantees a successful run.

The existing local review queue contains 12 development clips from six languages and zero human-verified references. It has no Japanese coverage or untouched final set. These clips have not been authorized for training by this workflow. Previously tested commercial recordings and model-generated lyrics must not become training references automatically.

Preparation performed locally: `.venv-training` has PyTorch `2.8.0+cu128`, the RTX 5080 passed a CUDA forward/backward probe and a random tiny-Whisper gradient check, and the original Small base was downloaded to `.runtime/whisper-small-training-base` at revision `973afd24965f72e36ca33b3055d56a652f456b4d`. No singing fine-tuning has run. The application environment remains on its existing CPU PyTorch, with GPU ASR handled by CTranslate2.

## Environment

From the repository root, create an isolated environment and install a pinned CUDA-enabled PyTorch build. The following commands target the documented Blackwell-compatible CUDA 12.8 build; do not run them in the application's environment:

```powershell
.\.venv311\Scripts\python.exe -m venv .venv-training
.\.venv\Scripts\uv.exe pip install --python .venv-training/Scripts/python.exe torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\uv.exe pip install --python .venv-training/Scripts/python.exe -e './lyriclens-app/backend[training,tools,test]'
.\.venv-training\Scripts\python.exe -m lyriclens.finetune hardware
```

These are explicit dependency downloads. The hardware command performs a tiny CUDA forward/backward probe without loading recognition weights. CPU training is available only with explicit `--device cpu`; there is no automatic device fallback. Stop heavy inference jobs before training. The separate environment does not install Demucs or modify the app's CPU separation environment.

## Data and human review

The current source selection follows [TRAINING_SOURCES.md](TRAINING_SOURCES.md): original contributor material is preferred; GTSinger, CSD and sources with restrictive/ambiguous terms are not admitted to this training selection. Even an eligible declared license requires a human review of component rights and local documentary evidence. No dataset is automatically approved from a license label.

Follow [BENCHMARK.md](BENCHMARK.md) to prepare and verify references. Before human verification, set `training_allowed: true` and add a nonempty `training_permission` field documenting permission for the audio, reference text and model adaptation. Changing either field invalidates an earlier review because the annotation fingerprint covers it. A license/source description alone is not an automatic training attestation; ambiguous or restricted material stays pending.

Each training/validation example must be manually aligned, single-language, nonempty sung text and at most 30 seconds. The first trainer rejects mixed-language clips and longer recordings instead of truncating them. Review shorter aligned excerpts separately. Include diverse singers, songs, accompaniment and difficult phonetic examples rather than only one song or its repeated choruses. A reference can come from authorized dataset annotation, but must still be checked against the audio.

Use development clips only for train/validation. Create `.runtime/training-assignment.json` with explicit clip IDs:

```json
{"train":["TRAIN_CLIP_ID"],"validation":["OTHER_SONG_CLIP_ID"]}
```

This illustrates the format, not a sufficient dataset size. Training and validation must have disjoint song/recording/singer-session groups and audio hashes. Final clips cannot appear in either list. The review gate checks the whole manifest, hashes and review fingerprints. No command certifies a human reviewer or invents reference lyrics.

An intentionally empty template is in [training-assignment.example.json](../evaluation/training-assignment.example.json). Populate IDs only after reviewing group relationships and permissions.

## Freeze the base and plan

Use the original Hugging Face `openai/whisper-small` trainable checkpoint, not the application's converted CTranslate2 binary. Resolve and record an exact 40-character commit SHA from the official model repository. Use that same SHA below; moving branches such as `main` are rejected:

```powershell
# The base preparation below has already been performed on this machine.
.\.venv-training\Scripts\python.exe -m lyriclens.finetune prepare-base .runtime/whisper-small-training-base --revision 973afd24965f72e36ca33b3055d56a652f456b4d
.\.venv-training\Scripts\python.exe -m lyriclens.finetune plan .runtime/reviewed-v1.jsonl .runtime/training-assignment.json .runtime/training-plan-v1.json --base-revision 973afd24965f72e36ca33b3055d56a652f456b4d --epochs 3
```

Only `prepare-base` downloads weights. It restricts downloads to Small weights/tokenizer/config files; a ready marker is written after completion. Planning performs no inference or training. It records manifest hash, explicit assignments, hyperparameters, seed, base revision, language coverage (including zeros), and duration. A changed plan or manifest is rejected at training time. No historical accuracy claim applies to this candidate.

## Train and inspect validation

```powershell
.\.venv-training\Scripts\python.exe -m lyriclens.finetune train .runtime/training-plan-v1.json .runtime/whisper-small-training-base .runtime/training-run-v1 --device cuda
```

This runs offline from local safetensors. Audio is decoded with FFmpeg and checked against reviewed duration; input features are cached temporarily on disk, and overlong decoder targets fail rather than being truncated. Each example gets its own language/transcription prefix. Training saves full HF checkpoints with safetensors after each epoch and generates validation hypotheses with CER/WER using the project's unchanged normalization. Empty/unsupported cases retain the evaluator's semantics.

Every epoch is retained; no automatic winner is installed. `history.json` contains validation text and metrics and must remain private where data permissions require it. Environment/hardware and the frozen training plan are retained. Successful completion writes `COMPLETE.json`; failures write `FAILED.json` after training output creation. Existing output directories are never overwritten. There is no optimizer-resume feature yet: choose a new output directory for a deliberate new run. CUDA out-of-memory errors are not silently retried with changed settings.

## Convert and compare

Choose an epoch using validation only:

```powershell
.\.venv-training\Scripts\python.exe -m lyriclens.finetune convert .runtime/training-run-v1/epoch-1 .runtime/whisper-small-candidate-v1
.\.venv311\Scripts\python.exe -m lyriclens.evaluate .runtime/reviewed-v1.jsonl --require-reviewed --split development --candidate .runtime/whisper-small-candidate-v1 --device cuda --compute float16 --output .runtime/candidate-development-v1.json
```

Conversion needs CTranslate2 in the training environment (`uv pip install --python .venv-training/Scripts/python.exe ctranslate2==4.8.3`). It converts local safetensors to a new directory, retains a local tokenizer/feature extractor, hashes the binary and marks the candidate **not approved for the app**. No network access or automatic cache installation is used. Candidate evaluation requires reviewed references and verifies the binary hash. Run baseline evaluation on exactly the same clips/settings and compare through `lyriclens.benchmark compare`; failed routes must remain in the report. Separate training/validation metrics from unseen development/final metrics: the entire development manifest may contain training examples, so its aggregate is not an independent generalization result.

After choosing a candidate and settings, evaluate once on a separate, reviewed final manifest using `--split final`. Keep that final data untouched during tuning. Evaluate every intended language and disclose coverage/failures. Installing a candidate into the app remains a separate explicit action after reviewing baseline/final results; no promotion command is included. This workflow does not claim to have fixed “Love You Anyway” or lowered CER in any language.

Implementation references: [Transformers 4.49 Whisper](https://huggingface.co/docs/transformers/v4.49.0/en/model_doc/whisper), [CTranslate2 Transformers conversion](https://opennmt.net/CTranslate2/guides/transformers.html), [official PyTorch Blackwell/CUDA 12.8 announcement](https://pytorch.org/blog/pytorch-2-7/), [PyTorch pinned installation commands](https://pytorch.org/get-started/previous-versions/).
