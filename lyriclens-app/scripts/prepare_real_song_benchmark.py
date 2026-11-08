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


REQUIRED = ('id', 'group_id', 'language', 'split', 'audio_path',
            'reference_path', 'reference_source', 'permissions')


def inspect_collection(collection, minimum=2):
    """Check all collection slots without importing or certifying human review."""
    if minimum < 1:
        raise ValueError('Minimum coverage must be positive.')
    rows, issues = [], []
    ids, hashes, groups = set(), {}, {}
    with collection.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        missing = [key for key in (*REQUIRED, *CONDITIONS) if key not in (reader.fieldnames or [])]
        if missing:
            issues.append(dict(line=1, id='', problems=['Missing CSV columns: ' + ', '.join(missing)]))
        slots = 0
        for number, entry in enumerate(reader, 2):
            slots += 1
            entry = {key: (value or '').strip() for key, value in entry.items() if key is not None}
            identifier = entry.get('id', '')
            problems = [f'fill {key} before preparing.' for key in REQUIRED if not entry.get(key)]
            if identifier in ids:
                problems.append('Duplicate recording ID.')
            ids.add(identifier)
            if entry.get('language') not in LANGUAGES:
                problems.append('Invalid language.')
            if entry.get('split') not in {'development', 'final'}:
                problems.append('Invalid split.')
            conditions = {}
            for key in CONDITIONS:
                value = entry.get(key, '').lower()
                if value not in {'true', 'false'}:
                    problems.append(f'{key} must be true or false after listening.')
                conditions[key] = value == 'true'
            audio = (collection.parent / entry.get('audio_path', '')).resolve()
            reference = (collection.parent / entry.get('reference_path', '')).resolve()
            duration, digest, text = None, None, None
            if entry.get('audio_path'):
                try:
                    with wave.open(str(audio), 'rb') as stream:
                        duration = stream.getnframes() / stream.getframerate()
                    if not math.isfinite(duration) or not 0 < duration <= 600:
                        problems.append('Audio must be longer than zero and at most 10 minutes.')
                    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
                except (OSError, wave.Error, EOFError) as exc:
                    problems.append(f'Cannot read PCM WAV audio: {exc}')
            if entry.get('reference_path'):
                try:
                    text = reference.read_text(encoding='utf-8-sig').strip()
                except (OSError, UnicodeError) as exc:
                    problems.append(f'Cannot read UTF-8 reference: {exc}')
            for mapping, key in ((hashes, digest), (groups, entry.get('group_id'))):
                if key:
                    splits = mapping.setdefault(key, set())
                    splits.add(entry.get('split'))
                    if len(splits) > 1:
                        problems.append('Related groups or identical audio cannot span development and final.')
            if problems:
                issues.append(dict(line=number, id=identifier, problems=problems))
                continue
            rows.append(dict(id=identifier, group_id=entry['group_id'], path=str(audio), sha256=digest,
                             language=entry['language'], split=entry['split'], duration=duration,
                             reference=text, reference_source=entry['reference_source'], permissions=entry['permissions'],
                             conditions=conditions, language_switching=conditions['language_switching'],
                             review={'status': 'pending', 'reviewer': '', 'listened': False,
                                     'text_permission_checked': False}))
    if not slots:
        issues.append(dict(line=1, id='', problems=['The collection CSV has no recordings.']))
    coverage, gaps = {}, []
    for split in ('development', 'final'):
        selected = [row for row in rows if row['split'] == split]
        languages = {lang: len({row['group_id'] for row in selected if row['language'] == lang})
                     for lang in sorted(LANGUAGES)}
        conditions = {key: len({row['group_id'] for row in selected if row['conditions'][key]})
                      for key in CONDITIONS}
        coverage[split] = dict(language_groups=languages, condition_groups=conditions)
        gaps.extend(f'{split}: {key} needs {minimum-count} more independent group(s) pending human review'
                    for key, count in {**languages, **conditions}.items() if count < minimum)
    report = dict(slots=slots, valid_recordings=len(rows), invalid_slots=slots-len(rows),
                  ready_for_import=not issues, human_review_required=True,
                  ready_for_representative_comparison=False, minimum_independent_groups=minimum,
                  coverage=coverage, coverage_gaps=gaps, issues=issues,
                  interpretation='Coverage uses structurally valid collection rows, not verified evidence. '
                                 'All references require human listening and review before benchmark evaluation.')
    return report, rows


def prepare(collection, output):
    if output.exists():
        raise ValueError('Output already exists; choose a new manifest version.')
    report, rows = inspect_collection(collection)
    if report['issues']:
        issue = report['issues'][0]
        raise ValueError(f"CSV line {issue['line']}: " + '; '.join(issue['problems']))
    with output.open('x', encoding='utf-8') as handle:
        handle.write('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n')
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', type=Path)
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--check', action='store_true', help='List all collection problems without importing')
    parser.add_argument('--report', type=Path, help='Write a new JSON check report without reference lyrics')
    parser.add_argument('--minimum-groups', type=int, default=2)
    args = parser.parse_args()
    try:
        if args.check:
            if args.output:
                parser.error('Do not supply a manifest output with --check; use --report.')
            report, _ = inspect_collection(args.collection, args.minimum_groups)
            contents = json.dumps(report, ensure_ascii=False, indent=2)
            if args.report:
                with args.report.open('x', encoding='utf-8') as handle:
                    handle.write(contents + '\n')
            print(contents)
            if not report['ready_for_import']:
                parser.exit(1)
        else:
            if not args.output or args.report:
                parser.error('Supply a manifest output, or use --check with optional --report.')
            print(f'Prepared {prepare(args.collection, args.output)} recordings; human review is still required.')
    except (ValueError, OSError, wave.Error, EOFError) as exc:
        parser.exit(1, f'{exc}\n')
