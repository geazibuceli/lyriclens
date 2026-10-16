"""Explicit model preparation; application requests never download weights."""
import argparse
import hashlib
import json
import urllib.request
from .config import Settings
from .profiles import profile_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download", "separation-download", "status"])
    parser.add_argument("--profile", choices=["configured", "large-v3"], default="configured")
    args = parser.parse_args()
    settings = profile_settings(Settings(), args.profile)
    if args.action == "status":
        print(json.dumps({"model": settings.model_id, "revision": settings.revision,
                          "prepared": (settings.model_dir / "READY.json").exists()}))
    elif args.action == "download":
        from huggingface_hub import snapshot_download
        print(f"Downloading {settings.model_id}@{settings.revision} from Hugging Face. Audio is never uploaded.")
        settings.model_dir.mkdir(parents=True, exist_ok=True)
        snapshot_download(settings.model_id, revision=settings.revision, local_dir=settings.model_dir,
                          allow_patterns=["model.bin", "config.json", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
        (settings.model_dir / "READY.json").write_text(json.dumps({"model": settings.model_id, "revision": settings.revision}), encoding="utf-8")
    else:
        folder = settings.root / "separation-models"
        folder.mkdir(parents=True, exist_ok=True)
        filename = "955717e8-8726e21a.th"
        target = folder / filename
        temporary = folder / (filename + ".partial")
        url = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/" + filename
        print(f"Downloading optional htdemucs checkpoint from {url}")
        try:
            urllib.request.urlretrieve(url, temporary)
            if not hashlib.sha256(temporary.read_bytes()).hexdigest().startswith("8726e21a"):
                raise ValueError("Checkpoint checksum mismatch")
            temporary.replace(target)
            (folder / "htdemucs.yaml").write_text("models: ['955717e8']\n", encoding="utf-8")
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
