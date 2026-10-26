"""Convert a completed real-song collection CSV into a pending-review manifest.

Run from any directory. Audio must be PCM WAV; no downloads or model inference.
Paths in the CSV are relative to the CSV. References must come from listening
and an authorized source. This command never marks a human review complete.
"""
import argparse
import csv
import hashlib
import json
import math
import wave
from pathlib import Path

LANGUAGES = {'ko', 'ja', 'zh', 'en', 'es', 'pt', 'fr'}
CONDITIONS = ('full_song', 'accompaniment', 'overlapping_vocals', 'repetition',
              'degraded_recording', 'language_switching')


def prepare(collection, output):
    if output.exists():
        raise ValueError('Output already exists; choose a new manifest version.')
    rows = []
    ids, hashes, groups = set(), {}, {}
    with collection.open(encoding='utf-8-sig', newline='') as handle:
        for number, entry in enumerate(csv.DictReader(handle), 2):
            for key in ('id', 'group_id', 'language', 'split', 'audio_path',
                        'reference_path', 'reference_source', 'permissions'):
                if not entry.get(key, '').strip():
                    raise ValueError(f'CSV line {number}: fill {key} before preparing.')
            identifier = entry['id'].strip()
            if identifier in ids or entry['language'] not in LANGUAGES or entry['split'] not in {'development', 'final'}:
                raise ValueError(f'CSV line {number}: invalid ID, language or split.')
            ids.add(identifier)
            audio = (collection.parent / entry['audio_path']).resolve()
            reference = (collection.parent / entry['reference_path']).resolve()
            with wave.open(str(audio), 'rb') as stream:
                duration = stream.getnframes() / stream.getframerate()
            if not math.isfinite(duration) or not 0 < duration <= 600:
                raise ValueError(f'{identifier}: audio must be longer than zero and at most 10 minutes.')
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            group = entry['group_id'].strip()
            for mapping, key in ((hashes, digest), (groups, group)):
                if key in mapping and mapping[key] != entry['split']:
                    raise ValueError('Related groups or identical audio cannot span development and final.')
                mapping[key] = entry['split']
            conditions = {}
            for key in CONDITIONS:
                value = entry.get(key, '').strip().lower()
                if value not in {'true', 'false'}:
                    raise ValueError(f'{identifier}: {key} must be true or false after listening.')
                conditions[key] = value == 'true'
            rows.append(dict(id=identifier, group_id=group, path=str(audio), sha256=digest,
                             language=entry['language'], split=entry['split'], duration=duration,
                             reference=reference.read_text(encoding='utf-8-sig').strip(),
                             reference_source=entry['reference_source'], permissions=entry['permissions'],
                             conditions=conditions, language_switching=conditions['language_switching'],
                             review={'status': 'pending', 'reviewer': '', 'listened': False,
                                     'text_permission_checked': False}))
    if not rows:
        raise ValueError('The collection CSV has no recordings.')
    with output.open('x', encoding='utf-8') as handle:
        handle.write('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n')
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        print(f'Prepared {prepare(args.collection, args.output)} recordings; human review is still required.')
    except (ValueError, OSError, wave.Error) as exc:
        parser.exit(1, f'{exc}\n')
