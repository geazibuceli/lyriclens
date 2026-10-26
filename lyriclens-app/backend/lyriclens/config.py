import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGES = {"ko": "Korean", "ja": "Japanese", "zh": "Mandarin Chinese", "en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French"}


def ffmpeg_executable():
    explicit = os.getenv("LYRICLENS_FFMPEG")
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


@dataclass
class Settings:
    root: Path = field(default_factory=lambda: Path(os.getenv("LYRICLENS_DATA", str(Path(__file__).resolve().parents[2] / "data"))).resolve())
    model_id: str = os.getenv("LYRICLENS_MODEL", "Systran/faster-whisper-small")
    revision: str = os.getenv("LYRICLENS_REVISION", "2ec96c5472da50d38d40c0cfe0602af2e94b4c8a")
    device: str = os.getenv("LYRICLENS_DEVICE", "cpu")
    compute_type: str = os.getenv("LYRICLENS_COMPUTE", "int8")
    separation_device: str = os.getenv("LYRICLENS_SEPARATION_DEVICE", "cpu")
    word_timestamps: bool = False
    hallucination_silence_threshold: float | None = None
    vad_filter: bool = False
    max_bytes: int = int(os.getenv("LYRICLENS_MAX_BYTES", str(150 * 1024 * 1024)))
    max_seconds: float = float(os.getenv("LYRICLENS_MAX_SECONDS", "600"))
    queue_size: int = int(os.getenv("LYRICLENS_QUEUE_SIZE", "8"))
    decode_timeout: int = int(os.getenv("LYRICLENS_DECODE_TIMEOUT", "30"))
    separation_timeout: int = int(os.getenv("LYRICLENS_SEPARATION_TIMEOUT", "600"))
    ffmpeg: str = field(default_factory=ffmpeg_executable)

    @property
    def model_dir(self):
        import hashlib
        key = hashlib.sha256(f"{self.model_id}@{self.revision}".encode()).hexdigest()[:20]
        return self.root / "models" / key

    def inference(self):
        return {"task": "transcribe", "beam_size": 5, "temperature": 0.0,
                "condition_on_previous_text": False, "vad_filter": self.vad_filter,
                "no_speech_threshold": 0.6, "log_prob_threshold": -1.0,
                "compression_ratio_threshold": 2.4, "word_timestamps": self.word_timestamps,
                **({'hallucination_silence_threshold': self.hallucination_silence_threshold}
                   if self.hallucination_silence_threshold is not None else {}),
                **({'vad_parameters': {'threshold': 0.1, 'min_silence_duration_ms': 10000,
                                       'speech_pad_ms': 3000}} if self.vad_filter else {})}
