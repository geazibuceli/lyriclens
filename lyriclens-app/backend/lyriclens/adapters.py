"""Replaceable local adapters. Import heavy dependencies only when requested."""
import json
import subprocess
import sys
import logging
import os
import importlib.util
import multiprocessing
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Protocol
from .domain import validate_model_segments

_CUDA_DLL_HANDLES = []


def digital_silence(audio):
    """Only exact zero-valued PCM16 counts; do not classify quiet singing as silence."""
    try:
        with wave.open(str(audio), "rb") as wav:
            return wav.getsampwidth() == 2 and wav.getnframes() > 0 and not any(wav.readframes(wav.getnframes()))
    except (OSError, wave.Error, EOFError):
        return False


def prepare_cuda_libraries():
    """Expose explicitly installed NVIDIA wheel DLLs on Windows; never install them."""
    if os.name != "nt" or _CUDA_DLL_HANDLES:
        return
    spec = importlib.util.find_spec("nvidia")
    if spec and spec.submodule_search_locations:
        for root in spec.submodule_search_locations:
            for directory in Path(root).glob("*/bin"):
                _CUDA_DLL_HANDLES.append(os.add_dll_directory(str(directory)))
                os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")


class Decoder(Protocol):
    def decode(self, source: Path, target: Path) -> dict: ...


class Transcriber(Protocol):
    def transcribe(self, audio: Path, language: str | None) -> dict: ...


class Separator(Protocol):
    def separate(self, audio: Path, directory: Path) -> Path: ...


class Aligner(Protocol):
    def align(self, audio: Path, segments: list, language: str) -> list: ...


class FFmpegDecoder:
    def __init__(self, settings):
        self.settings = settings

    def crop(self, source, target, start, end):
        try:
            subprocess.run([self.settings.ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(source),
                            "-ss", str(start), "-t", str(end-start), "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", str(target)], check=True, capture_output=True,
                           timeout=self.settings.decode_timeout)
        except subprocess.TimeoutExpired:
            raise ValueError("Audio region extraction exceeded its time limit") from None
        except (OSError, subprocess.CalledProcessError):
            raise ValueError("Audio region extraction failed") from None
        with wave.open(str(target), "rb") as audio:
            return audio.getnframes() / audio.getframerate()

    def decode(self, source, target):
        # Decode only limit + 1 second: reject rather than silently truncate long inputs.
        command = [self.settings.ffmpeg, "-nostdin", "-v", "error", "-y",
                   "-protocol_whitelist", "file,pipe", "-format_whitelist", "wav,mp3,flac,mov",
                   "-i", str(source), "-map", "0:a:0",
                   "-t", str(self.settings.max_seconds + 1), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=self.settings.decode_timeout)
            with wave.open(str(target), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            if duration <= 0 or duration > self.settings.max_seconds:
                raise ValueError(f"Audio must be between 0 and {self.settings.max_seconds:g} seconds")
            return {"duration": duration, "sample_rate": 16000, "channels": 1,
                    "decoder": "FFmpeg", "timeline": "identity; no silence removed"}
        except FileNotFoundError:
            raise ValueError("FFmpeg is unavailable. Install FFmpeg and restart the service.") from None
        except subprocess.TimeoutExpired:
            raise ValueError("Audio decoding exceeded its time limit") from None
        except (subprocess.CalledProcessError, wave.Error, EOFError):
            raise ValueError("Audio could not be decoded. Use a valid WAV, MP3, FLAC, M4A, or MP4 file containing an audio track.") from None


class WhisperTranscriber:
    def __init__(self, settings):
        self.settings = settings
        self.model = None

    def transcribe(self, audio, language):
        if digital_silence(audio):
            return {"segments":[],"raw_segments":[],"language":language,
                    "language_source":"user instruction" if language else "not detected: digital silence",
                    "model_executed":False,"raw_transcription_info":None,
                    "signal_control":"All decoded PCM16 samples are exactly zero; model inference skipped"}
        if not (self.settings.model_dir / "READY.json").exists():
            raise ValueError("Model is not prepared. Run python -m lyriclens.models download explicitly.")
        try:
            return self._infer(audio,language)
        except Exception:
            logging.getLogger("lyriclens").exception("Local ASR adapter failed")
            raise ValueError("Local transcription failed. Check prepared model files, inference dependencies and device libraries in the local server log.") from None

    def _infer(self,audio,language):
        if self.model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise ValueError("Install the inference dependency group first") from None
            if self.settings.device == "cuda":
                prepare_cuda_libraries()
            self.model = WhisperModel(str(self.settings.model_dir), device=self.settings.device,
                                      compute_type=self.settings.compute_type, local_files_only=True)
        def recognize(options):
            segments, info = self.model.transcribe(str(audio), language=language, **options)
            raw = [asdict(s) for s in segments]
            return {"segments": [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in raw],
                    "raw_segments": raw, "language": info.language,
                    "language_source": "user instruction" if language else "whole-clip model estimate",
                    "language_probability_score": info.language_probability,
                    "raw_transcription_info": asdict(info), "model_executed": True}

        options = self.settings.inference()
        initial = recognize(options)
        if options.get('word_timestamps'):
            return initial
        with wave.open(str(audio), 'rb') as source:
            duration = source.getnframes() / source.getframerate()
        try:
            validate_model_segments(initial['segments'], duration)
            return initial
        except ValueError:
            if all(0 <= segment['start'] < segment['end'] <= duration for segment in initial['segments']):
                return initial  # Other schema errors must not trigger a timing retry.
        recovery = dict(strategy='same-model native word alignment', initial_response=initial,
                        succeeded=False, effective_settings={**options, 'word_timestamps': True})
        try:
            aligned = recognize(recovery['effective_settings'])
        except Exception:
            logging.getLogger('lyriclens').exception('Timestamp recovery inference failed')
            return {**initial, 'timing_recovery': {**recovery, 'error': 'Native alignment retry failed; inspect local server log.'}}
        try:
            validate_model_segments(aligned['segments'], duration)
            recovery['succeeded'] = True
        except ValueError:
            pass  # Preserve the second response; the caller still rejects invalid timing.
        return {**aligned, 'timing_recovery': recovery}


class DemucsSeparator:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.connection = None

    def separate(self, audio, directory):
        if digital_silence(audio):
            # Demucs normalizes by signal variance and cannot process all-zero audio.
            return audio
        repo = self.settings.root / "separation-models"
        if not (repo / "955717e8-8726e21a.th").exists():
            raise ValueError("Vocal model unavailable. Run python -m lyriclens.models separation-download explicitly, or use Direct.")
        target = directory / "htdemucs" / audio.stem / "vocals.wav"
        try:
            if self.process is None or not self.process.is_alive():
                self.close()
                context = multiprocessing.get_context("spawn")
                self.connection, child = context.Pipe()
                self.process = context.Process(target=_separation_worker,
                                               args=(child,str(repo),self.settings.separation_device),daemon=True)
                self.process.start()
                child.close()
            self.connection.send((str(audio),str(target)))
            if not self.connection.poll(self.settings.separation_timeout):
                self.close()
                raise ValueError("Vocal separation exceeded its time limit; try Direct")
            status, details = self.connection.recv()
            if status != "completed":
                logging.getLogger("lyriclens").error("Demucs worker failed: %s",details)
                raise ValueError("Vocal separation failed. Check optional dependencies and the local log, or try Direct.")
            return target
        except (OSError, EOFError, BrokenPipeError):
            self.close()
            raise ValueError("Vocal separation process stopped unexpectedly; try Direct") from None

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                try:
                    self.connection.send(None)
                except (OSError,EOFError):
                    pass
                self.process.join(timeout=1)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=2)
            self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def _separation_worker(connection, repo, device):
    """Keep one Demucs model in an isolated, timeout-terminable local process."""
    try:
        import torch
        import torchaudio
        from demucs.pretrained import get_model
        from demucs.audio import convert_audio
        from demucs.apply import apply_model
        torch.set_num_threads(min(4,os.cpu_count() or 1))
        model = get_model("htdemucs",repo=Path(repo)).to(device).eval()
        while True:
            request = connection.recv()
            if request is None:
                return
            source, target = request
            try:
                wav, rate = torchaudio.load(source)
                wav = convert_audio(wav,rate,model.samplerate,model.audio_channels)
                ref = wav.mean(0)
                deviation = ref.std()
                if not torch.isfinite(deviation) or deviation <= 0:
                    raise ValueError("Vocal separation requires a nonconstant audio signal")
                normalized = (wav-ref.mean())/deviation
                with torch.inference_mode():
                    stems = apply_model(model,normalized[None],device=device,shifts=0,split=True,overlap=.25,progress=False)[0]
                stems = stems*deviation+ref.mean()
                vocals = stems[model.sources.index("vocals")].cpu()
                Path(target).parent.mkdir(parents=True,exist_ok=True)
                torchaudio.save(target,vocals,model.samplerate,encoding="PCM_S",bits_per_sample=16)
                connection.send(("completed",None))
            except Exception:
                import traceback
                connection.send(("failed",traceback.format_exc()))
    except Exception:
        import traceback
        try:
            connection.send(("failed",traceback.format_exc()))
        except (OSError,EOFError):
            pass
    finally:
        connection.close()
