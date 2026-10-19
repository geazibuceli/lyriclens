# Model and dependency review

Optional text translation uses [Meta M2M100 418M](https://huggingface.co/facebook/m2m100_418M/tree/55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636), MIT-tagged, pinned revision `55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`, explicitly converted to CPU/int8 CTranslate2. It is separate from Whisper transcription and supports the seven product language codes. [Translation setup and verification](TRANSLATION.md) describe the independent model cache, dependencies and limits. Translation quality on lyrics has not been evaluated; 42 real short-sentence pair executions are smoke evidence only.

Reviewed official documentation on 2026-10-15. These are published capabilities and requirements, not application measurements.

| Target | Identifier | Speech exercised | Natural singing exercised | Singing quality evaluated |
|---|---|---|---|---|
| Korean | ko | Both pipelines | Both models/pipelines | 2 development clips |
| Japanese | ja | Both pipelines | Both models/pipelines; failures recorded | Not scored: no checked orthographic reference |
| Mandarin Chinese | zh | Both pipelines | Both models/pipelines | 2 development clips |
| English | en | Both pipelines | Both models/pipelines | 2 development clips |
| Spanish | es | Both pipelines | Both models/pipelines | 1 development clip |
| Portuguese | pt | Both pipelines | Both models/pipelines | 3 development clips, Brazilian samples |
| French | fr | Both pipelines | Both models/pipelines | 2 development clips |

See [singing measurements and restrictions](SINGING.md). These small mostly unaccompanied examples do not validate general singing accuracy. Large-v3 is an explicit experimental choice; its native cross-attention word alignment is enabled to improve segment timing. Raw word/segment responses remain available, while the UI continues to show approximate segment times. There is no separate alignment model download or invented word timing.

Automatic and manual speech runs are recorded separately. One clip per language is a diagnostic, not representative support evidence. See measured per-clip CER/WER, detection, runtime and memory in `evaluation/speech-results.json` and `evaluation/manual-speech-results.json`.

[Whisper tokenizer language registry](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py) includes these codes. [Whisper model card](https://github.com/openai/whisper/blob/main/model-card.md) concerns speech recognition and warns of hallucinations and variable language performance. It is not evidence of accurate singing transcription. Preserve kana/kanji, Hangul, Chinese characters, and accented Latin scripts exactly as emitted.

Selected ASR: [SYSTRAN converted Whisper Small model card](https://huggingface.co/Systran/faster-whisper-small/tree/2ec96c5472da50d38d40c0cfe0602af2e94b4c8a), MIT-tagged model weights derived from [OpenAI Whisper](https://github.com/openai/whisper), whose code and weights are MIT. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) implementation is MIT, uses CTranslate2, supports Python >=3.9 upstream, CPU int8 and NVIDIA CUDA inference. This application uses Python 3.11 as its full-stack baseline. Project source/release activity was visible at review; maintenance is not guaranteed. GPU requirements: CUDA 12 cuBLAS, cuDNN 9 for the current engine. Do not interpret upstream performance benchmarks as measurements of this application.

Explicit larger profile: [SYSTRAN converted Large-v3](https://huggingface.co/Systran/faster-whisper-large-v3/tree/edaa852ec7e145841d8ffdb056a99866b5f0a478), pinned revision edaa852ec7e145841d8ffdb056a99866b5f0a478, model.bin 3,087,284,237 bytes. Its upstream [OpenAI Large-v3 model card](https://huggingface.co/openai/whisper-large-v3) declares Apache-2.0; do not assume Small's model license automatically applies to this checkpoint. Preserve the checkpoint's distribution notices. This profile has been exercised on Windows CUDA float16; CPU Large-v3 performance and Docker Large-v3 execution have not been validated. It explicitly enables native word alignment; no runtime download, hidden model substitution or separate forced-alignment model is used.

Optional [Demucs](https://github.com/facebookresearch/demucs): MIT repository/code and pretrained models distributed under the project's stated MIT terms; htdemucs is selected by the [official model definition](https://raw.githubusercontent.com/facebookresearch/demucs/main/demucs/remote/htdemucs.yaml) and [checkpoint registry](https://raw.githubusercontent.com/facebookresearch/demucs/main/demucs/remote/files.txt). Repository is archived and unmaintained. Python 3.11.17 + PyTorch/torchaudio 2.5.1 + SoundFile 0.13.1 was executed successfully on Windows CPU. SoundFile is necessary for this torchaudio profile when no decoder backend is available. A persistent isolated process reuses the loaded separator, with `shifts=0`, overlap 0.25 and a hard per-operation timeout. Exact zero PCM bypasses it to avoid undefined variance normalization. Checkpoint source is Meta's public host. Do not install this optional group on Python 3.14. GPU separation is unverified. No model replacement is attempted.

Windows ASR CUDA/float16 was executed using CTranslate2 4.8.3, cuBLAS 12.9.2.10, cuDNN 9.27.0.42 and CUDA NVRTC 12.9.86. The initial run failed due to missing `cublas64_12.dll`; the explicit `cuda-windows` extra supplies those DLLs, which the adapter discovers locally. This does not install or replace GPU drivers, or change the requested model. CPU int8 remains independent.

Model revision changes require a new explicit preparation and evaluation. Hugging Face cache can be reused by its client; the app's revision-specific local folders are authoritative for runtime. Existing CTranslate2 files may be copied into the selected folder only with correct provenance and a matching READY.json. Never substitute a different revision under an existing marker.

Other dependencies: FastAPI and Starlette (MIT), Pydantic (MIT), Uvicorn (BSD-3-Clause), python-multipart (Apache-2.0), React (MIT), TypeScript (Apache-2.0), Vite (MIT), Lucide (ISC), PyTorch/torchaudio (BSD-style), Hugging Face Hub (Apache-2.0), CTranslate2 (MIT), pytest (MIT), HTTPX (BSD-3-Clause). FFmpeg license depends on build options (LGPL/GPL); consult the selected binary's license with `ffmpeg -L`. No FFmpeg binary or model weight is redistributed in the source repository. Preserve upstream license notices when distributing dependency bundles or Docker images. Dataset permissions are independent of implementation/model licenses.
