"""Check local inference on complete development songs without scoring lyrics.

Publisher lyrics with abbreviated refrains are not reviewed ASR references.
This runner records execution/timestamp validity only; it never computes CER/WER.
Raw transcriptions stay under the explicitly selected local output directory.
"""
import argparse
import gc
import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from lyriclens.adapters import WhisperTranscriber
from lyriclens.config import Settings
from lyriclens.domain import validate_model_segments
from lyriclens.evaluate import load_manifest
from lyriclens.profiles import profile_settings
from lyriclens.worker import environment


def run(manifest, output, device='cpu', compute='int8'):
    rows = load_manifest(manifest)
    if not rows or any(row['split'] != 'development' or
                       row.get('conditions', {}).get('full_song') is not True for row in rows):
        raise ValueError('Select a nonempty complete-song development manifest')
    output.mkdir(parents=True, exist_ok=False)
    runs = []
    for profile in ('configured', 'large-v3'):
        settings = profile_settings(replace(Settings(), device=device, compute_type=compute), profile)
        transcriber = WhisperTranscriber(settings)
        for row in rows:
            result = dict(id=row['id'], title=row.get('title', row['id']),
                          audio_sha256=row['sha256'], duration=row['duration'],
                          group_id=row['group_id'], profile=profile, model=settings.model_id,
                          revision=settings.revision, device=device, compute_type=compute,
                          settings=settings.inference(), pipeline='direct', language_mode='manual')
            started = time.perf_counter()
            try:
                raw = transcriber.transcribe(row['resolved_path'], row['language'])
                segments, reordered = validate_model_segments(raw['segments'], row['duration'])
                filename = hashlib.sha256(row['id'].encode()).hexdigest()[:16] + f'-{profile}.json'
                with (output / filename).open('x', encoding='utf-8') as handle:
                    json.dump(raw, handle, ensure_ascii=False, indent=2)
                recovery = raw.get('timing_recovery', {})
                result.update(state='completed', segments=len(segments),
                              timestamps_reordered=reordered,
                              model_executed=raw.get('model_executed', False),
                              timing_recovery_attempted=bool(recovery),
                              timing_recovery_succeeded=recovery.get('succeeded'),
                              empty_output=not segments)
            except Exception as exc:
                result.update(state='failed', error=str(exc))
            result['seconds'] = time.perf_counter() - started
            result['real_time_factor'] = result['seconds'] / row['duration']
            runs.append(result)
            print(f'{profile}: {row["id"]}: {result["state"]} ({result["seconds"]:.2f}s)', flush=True)
        del transcriber
        gc.collect()
    report = dict(
        executed_at=datetime.now(timezone.utc).isoformat(),
        purpose='Complete-song inference smoke check; no accuracy scoring',
        interpretation='Completion means inference returned structurally valid timestamps. '
                       'It does not mean the recognized words are correct or synchronized by human review. '
                       'Timing includes cold model loading on the first song and model reuse afterward.',
        human_review_required=True, accuracy_scored=False, independent_groups=len({row['group_id'] for row in rows}),
        final_recordings=0, manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        environment=environment(), attempted=len(runs), completed=sum(item['state'] == 'completed' for item in runs),
        per_run=runs,
    )
    with (output / 'summary.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path, help='New local output directory for raw responses and text-free summary')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--compute', default='int8')
    args = parser.parse_args()
    report = run(args.manifest, args.output, args.device, args.compute)
    if report['completed'] != report['attempted']:
        raise SystemExit(1)
