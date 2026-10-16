"""Licensed manifest evaluation, running identical audio through both adapters."""
import argparse
import hashlib
import json
import tempfile
import time
import unicodedata
from pathlib import Path
from dataclasses import replace
from .adapters import FFmpegDecoder, WhisperTranscriber, DemucsSeparator
from .config import Settings, LANGUAGES
from .domain import validate_segments, text_of
from .memory import PeakMemory
from .worker import environment
from .profiles import profile_settings


def normalize(text):
    # Keep diacritics, repeated lines, script distinctions, and case-folded letters.
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join("".join(" " if unicodedata.category(c).startswith("P") else c for c in text).split())


def distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        new = [i]
        for j, right in enumerate(hypothesis, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j-1] + (left != right)))
        row = new
    return row[-1]


def metrics(reference, hypothesis, language):
    ref, hyp = normalize(reference), normalize(hypothesis)
    ref_chars, hyp_chars = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
    cer_errors = distance(ref_chars, hyp_chars)
    result = {"normalized_reference": ref, "normalized_hypothesis": hyp,
              "cer": cer_errors / len(ref_chars) if ref_chars else (0.0 if not hyp_chars else None),
              "character_errors": cer_errors, "reference_characters": len(ref_chars),
              "empty_reference_insertions": len(hyp_chars) if not ref_chars else 0,
              "wer": None, "wer_method": "not applicable: no lexical segmentation implemented"}
    if language not in {"ja", "zh"}:
        words, output = ref.split(), hyp.split()
        result.update(wer=distance(words, output) / len(words) if words else (0.0 if not output else None),
                      word_errors=distance(words, output), reference_words=len(words),
                      wer_method="Unicode whitespace tokens; Korean spacing-sensitive")
    return result


def load_manifest(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = set()
    for row in rows:
        for key in ("id", "path", "sha256", "language", "reference", "reference_source", "permissions", "duration", "conditions", "language_switching", "split"):
            if key not in row:
                raise ValueError(f"Missing manifest field: {key}")
        if row["id"] in ids or row["language"] not in LANGUAGES or row["split"] not in {"development", "final"}:
            raise ValueError("Invalid clip id, language, or split")
        ids.add(row["id"])
        if not row["permissions"] or not row["reference_source"] or row["duration"] <= 0:
            raise ValueError("Permissions, reference source, and positive duration are required")
        if not isinstance(row["language_switching"], bool) or not isinstance(row["reference"], str):
            raise ValueError("Reference must be text and language_switching must be boolean")
        clip = (path.parent / row["path"]).resolve()
        if hashlib.sha256(clip.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Audio hash mismatch: {row['id']}")
        row["resolved_path"] = clip
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", required=True, choices=["development", "final"])
    parser.add_argument("--output", type=Path, default=Path("evaluation-report.json"))
    parser.add_argument("--manual-language", action="store_true", help="Default uses whole-clip detection")
    parser.add_argument("--model-profile",choices=["configured","large-v3"],default="configured")
    parser.add_argument("--device",choices=["cpu","cuda"])
    parser.add_argument("--compute",help="Explicit CTranslate2 compute type; no fallback")
    args = parser.parse_args()
    settings = profile_settings(Settings(),args.model_profile)
    if args.device:
        settings = replace(settings,device=args.device)
    if args.compute:
        settings = replace(settings,compute_type=args.compute)
    decoder, model, separator = FFmpegDecoder(settings), WhisperTranscriber(settings), DemucsSeparator(settings)
    reports = []
    for row in load_manifest(args.manifest):
        if row["split"] != args.split:
            continue
        for pipeline in ("direct", "vocals"):
            report = {k:v for k,v in row.items() if k != "resolved_path"}
            report.update(pipeline=pipeline, model=settings.model_id, revision=settings.revision, settings=settings.inference())
            report["environment"] = environment()
            report["inference_device"] = settings.device
            report["compute_type"] = settings.compute_type
            report["separator_settings"] = {"device":settings.separation_device,"shifts":0} if pipeline == "vocals" else None
            print(f"Running {row['id']}: {pipeline}",flush=True)
            memory = PeakMemory().start()
            started = time.perf_counter()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    directory = Path(tmp)
                    decoded = directory / "decoded.wav"
                    info = decoder.decode(row["resolved_path"], decoded)
                    if abs(info["duration"] - row["duration"]) > .1:
                        raise ValueError("Manifest duration does not match decoded audio")
                    audio = decoded
                    if pipeline == "vocals":
                        audio = directory / "vocals.wav"
                        vocal_info = decoder.decode(separator.separate(decoded, directory / "stems"), audio)
                        report["separator_process_id"] = separator.process.pid if separator.process else None
                        if abs(vocal_info["duration"] - info["duration"]) > .1:
                            raise ValueError("Separation timeline mismatch")
                    raw = model.transcribe(audio, row["language"] if args.manual_language else None)
                    report["raw"] = raw
                    validate_segments(raw["segments"], info["duration"])
                    hypothesis = text_of(raw["segments"])
                    report.update(state="completed", raw=raw, hypothesis=hypothesis,
                                  metrics=metrics(row["reference"], hypothesis, row["language"]),
                                  language_detection_correct=None if args.manual_language or row["language_switching"] or not row["reference"].strip() else raw.get("language") == row["language"])
            except Exception as exc:
                report.update(state="failed", error=str(exc))
            seconds = time.perf_counter() - started
            report.update(seconds=seconds, real_time_factor=seconds / row["duration"], peak_memory_bytes=memory.stop(),
                          memory_method="sampled process-tree summed RSS every 50ms; null when psutil unavailable; excludes VRAM")
            reports.append(report)
    summaries = []
    for language in LANGUAGES:
        for pipeline in ("direct", "vocals"):
            group = [r for r in reports if r["language"] == language and r["pipeline"] == pipeline]
            completed = [r for r in group if r["state"] == "completed"]
            count = sum(r["metrics"]["reference_characters"] for r in completed)
            word_count = sum(r["metrics"].get("reference_words", 0) for r in completed)
            labeled = [r for r in completed if r["language_detection_correct"] is not None]
            summaries.append({"language":language,"pipeline":pipeline,"status":"evaluated" if group else "not evaluated",
                              "clips":len(group),"failure_rate":1-len(completed)/len(group) if group else None,
                              "micro_cer":sum(r["metrics"]["character_errors"] for r in completed)/count if count else None,
                              "micro_wer":sum(r["metrics"].get("word_errors", 0) for r in completed)/word_count if word_count else None,
                              "mean_seconds":sum(r["seconds"] for r in group)/len(group) if group else None,
                              "mean_real_time_factor":sum(r["real_time_factor"] for r in group)/len(group) if group else None,
                              "max_sampled_rss_bytes":max((r["peak_memory_bytes"] for r in group if r["peak_memory_bytes"] is not None), default=None),
                              "language_detection_accuracy":sum(r["language_detection_correct"] for r in labeled)/len(labeled) if labeled else None})
    args.output.write_text(json.dumps({"split": args.split, "per_clip":reports,"per_language":summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    separator.close()
    print(f"Wrote {len(reports)} pipeline runs to {args.output}")


if __name__ == "__main__":
    main()
