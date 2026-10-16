"""Download a public-domain solo-singing fixture explicitly; no reference is inferred."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path
from lyriclens.config import Settings


def main():
    root = Path(__file__).resolve().parents[1]/"evaluation"
    folder = root/"audio"/"singing"
    folder.mkdir(parents=True,exist_ok=True)
    original = folder/"mary-original.ogg"
    url = "https://upload.wikimedia.org/wikipedia/commons/5/50/Mary_Had_a_Little_Lamb.ogg"
    request = urllib.request.Request(url,headers={"User-Agent":"LyricLens/0.1 local research smoke test"})
    with urllib.request.urlopen(request,timeout=60) as response:
        original.write_bytes(response.read(2*1024*1024))
    target = folder/"mary.wav"
    subprocess.run([Settings().ffmpeg,"-nostdin","-v","error","-y","-i",str(original),"-ac","1","-ar","16000","-c:a","pcm_s16le",str(target)],check=True,timeout=30)
    metadata = {"id":"mary-celestianpower-2006","path":"audio/singing/mary.wav",
                "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                "original_sha256":hashlib.sha256(original.read_bytes()).hexdigest(),
                "source":"https://commons.wikimedia.org/wiki/File:Mary_Had_a_Little_Lamb.ogg",
                "source_revision":452298650,"author":"Celestianpower","date":"2006-05-13",
                "permissions":"Recording dedicated to the public domain by its creator (PD-self); traditional composition/text public domain",
                "language":"en","conditions":"Solo unaccompanied singing; Ogg decoded to mono 16kHz PCM WAV without trimming",
                "content_type":"singing","reference":None,"reference_status":"Not manually verified; do not score WER/CER or infer reference from model output"}
    (root/"singing-smoke-source.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(f"Prepared public-domain singing fixture: {target}")


if __name__ == "__main__":
    main()
