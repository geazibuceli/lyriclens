"""Inspect local prerequisites without loading or downloading model weights."""
import json
import os
import shutil
import subprocess
from .config import Settings
from .worker import environment


def main():
    settings = Settings()
    report = {**environment(), "cpu_count": os.cpu_count(), "device": settings.device,
              "compute_type": settings.compute_type, "model": settings.model_id,
              "revision": settings.revision, "prepared": (settings.model_dir / "READY.json").exists()}
    try:
        report["ffmpeg"] = subprocess.run([settings.ffmpeg,"-version"],check=True,capture_output=True,text=True,timeout=10).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        report["ffmpeg"] = "unavailable"
    try:
        import ctranslate2
        report["cpu_compute_types"] = sorted(ctranslate2.get_supported_compute_types("cpu"))
        report["cuda_devices"] = ctranslate2.get_cuda_device_count()
    except (ImportError, RuntimeError) as exc:
        report["inference_check_error"] = str(exc)
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
