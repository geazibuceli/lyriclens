"""Explicitly fetch one CC-BY-4.0 FLEURS speech example per target; never a singing benchmark."""
import argparse
import hashlib
import json
import wave
import subprocess
from pathlib import Path
import fsspec
import pyarrow.parquet as pq

CONFIGS = {"ko":"ko_kr","ja":"ja_jp","zh":"cmn_hans_cn","en":"en_us","es":"es_419","pt":"pt_br","fr":"fr_fr"}
SOURCE = "https://huggingface.co/datasets/google/fleurs"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "evaluation"
    folder = root / "audio" / "fleurs"
    folder.mkdir(parents=True,exist_ok=True)
    rows = []
    manifest = root / "speech-smoke.jsonl"
    cached = {r["language"]:r for r in (json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip())} if manifest.exists() else {}
    for language in args.languages:
        config = CONFIGS[language]
        url = f"{SOURCE}/resolve/refs%2Fconvert%2Fparquet/{config}/test/0000.parquet"
        target = folder / f"{language}-0.wav"
        if language in cached and target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != cached[language]["sha256"]:
                raise ValueError(f"Cached {language} clip differs from its recorded hash")
            rows.append(cached[language])
            print(f"Reusing verified {language} fixture",flush=True)
            continue
        # HTTP range reads avoid downloading entire language archives.
        with fsspec.open(url,"rb",block_size=256*1024) as remote:
            parquet = pq.ParquetFile(remote)
            metadata = parquet.metadata.row_group(0)
            if metadata.total_byte_size > 1024*1024*1024:
                raise ValueError("First row group exceeds the smoke fixture download budget")
            print(f"Reading {language} row group ({metadata.total_byte_size/1024/1024:.1f} MiB); speech only",flush=True)
            row = parquet.read_row_group(0,columns=["audio","raw_transcription","transcription","num_samples"]).slice(0,1).to_pylist()[0]
        target.write_bytes(row["audio"]["bytes"])
        duration = row["num_samples"]/16000
        rows.append({"id":f"fleurs-{language}-test-row0", "path":str(target.relative_to(root)).replace("\\","/"),
                     "sha256":hashlib.sha256(target.read_bytes()).hexdigest(), "language":language,
                     "reference":row.get("raw_transcription") or row["transcription"],
                     "reference_source":f"{SOURCE}, {config}, test row 0, original FLEURS reference",
                     "permissions":"CC-BY-4.0; FLEURS by Conneau et al. (2022), Google; https://creativecommons.org/licenses/by/4.0/",
                     "duration":duration,"conditions":"Read speech from FLEURS; no singing or musical accompaniment; diagnostic only",
                     "language_switching":False,"split":"development","content_type":"speech"})
        print(f"Prepared {language}: {duration:.2f}s, {target.stat().st_size} bytes",flush=True)
        (root / "speech-smoke.jsonl").write_text("\n".join(json.dumps(r,ensure_ascii=False) for r in rows)+"\n",encoding="utf-8")
    (root / "speech-smoke.jsonl").write_text("\n".join(json.dumps(r,ensure_ascii=False) for r in rows)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
