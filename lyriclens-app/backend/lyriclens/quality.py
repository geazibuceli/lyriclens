"""Audit benchmark coverage and prepare reproducible robustness diagnostics."""
import argparse
import hashlib
import json
import math
import random
import subprocess
import wave
from array import array
from pathlib import Path

from .benchmark import checked, compare
from .config import LANGUAGES, Settings
from .evaluate import load_manifest
from .adapters import FFmpegDecoder

CONDITIONS = ('full_song', 'accompaniment', 'overlapping_vocals', 'repetition',
              'degraded_recording', 'language_switching')
VARIANTS = ('noise', 'telephone', 'reverb', 'repeated', 'long_repeated')


def conditions(row):
    value = row.get('conditions')
    return value if isinstance(value, dict) else {}


def audit(manifest, minimum=2):
    if minimum < 1:
        raise ValueError('Minimum coverage must be positive')
    rows = load_manifest(manifest)
    verified = [r for r in rows if checked(r) and r.get('group_id', '').strip()]
    real = [r for r in verified if not conditions(r).get('synthetic')]
    problems = []
    for field in ('sha256', 'group_id'):
        splits = {}
        for row in rows:
            if row.get(field):
                splits.setdefault(row[field], set()).add(row['split'])
        if any(len(value) > 1 for value in splits.values()):
            problems.append(f'Development/final leakage in {field}')
    coverage = {}
    for split in ('development', 'final'):
        selected = [r for r in real if r['split'] == split]
        languages = {lang: len({r['group_id'] for r in selected if r['language'] == lang}) for lang in LANGUAGES}
        cases = {key: len({r['group_id'] for r in selected if
                           (r['language_switching'] if key == 'language_switching' else conditions(r).get(key) is True)})
                 for key in CONDITIONS}
        coverage[split] = dict(reviewed_real_clips=len(selected), language_groups=languages, condition_groups=cases)
        problems.extend(f'{split}: {key} needs {minimum-count} more reviewed independent group(s)'
                        for key, count in {**languages, **cases}.items() if count < minimum)
    return dict(clips=len(rows), reviewed=len(verified), pending=len(rows)-len(verified),
                synthetic_clips=sum(bool(conditions(r).get('synthetic')) for r in rows),
                minimum_independent_groups=minimum, coverage=coverage,
                ready_for_representative_comparison=not problems, gaps=problems,
                interpretation='Coverage counts human-reviewed original recordings by song/session group. '
                               'Synthetic fixtures are reported separately. Coverage readiness is a collection threshold, '
                               'not an accuracy score or statistical validation.')


def stress(manifest, output, ids, variants, seed=1729):
    rows = load_manifest(manifest)
    selected = [r for r in rows if r['id'] in ids]
    if len(ids) != len(set(ids)) or len(selected) != len(ids) or not selected:
        raise ValueError('Select existing unique recording IDs')
    if len(variants) != len(set(variants)) or any(variant not in VARIANTS for variant in variants):
        raise ValueError('Select unique supported robustness variants')
    if any(r['split'] != 'development' for r in selected):
        raise ValueError('Robustness generation uses development recordings only')
    if output.exists():
        raise ValueError('Output directory exists; use a new version')
    output.mkdir(parents=True)
    decoder = FFmpegDecoder(Settings())
    generated = []
    for row in selected:
        # Source IDs are data, not filesystem paths.
        stem = hashlib.sha256(row['id'].encode()).hexdigest()[:12]
        decoded = output/f'{stem}-original.wav'
        info = decoder.decode(row['resolved_path'], decoded)
        if abs(info['duration'] - row['duration']) > .1:
            raise ValueError('Source duration differs from manifest')
        for variant in ('original', *variants):
            target = decoded if variant == 'original' else output/f'{stem}-{variant}.wav'
            repeats = 1
            if variant in {'noise', 'repeated', 'long_repeated'}:
                with wave.open(str(decoded), 'rb') as source:
                    samples = array('h', source.readframes(source.getnframes()))
                    rate = source.getframerate()
                if variant == 'noise':
                    rng = random.Random(f'{seed}:{row["sha256"]}')
                    rms = math.sqrt(sum(float(s)*s for s in samples)/len(samples))
                    sigma = rms/(10**(10/20))  # deterministic additive noise, target SNR 10 dB
                    samples = array('h', (max(-32768, min(32767, round(s+rng.gauss(0, sigma)))) for s in samples))
                else:
                    repeats = 3 if variant == 'repeated' else max(2, math.ceil(120/info['duration']))
                    if repeats*info['duration'] > 600:
                        raise ValueError('Repeated fixture exceeds the application duration limit')
                    samples *= repeats
                with wave.open(str(target), 'wb') as destination:
                    destination.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                    destination.writeframes(samples.tobytes())
            elif variant in {'telephone', 'reverb'}:
                effect = 'highpass=f=300,lowpass=f=3400' if variant == 'telephone' else 'aecho=0.8:0.5:60:0.25'
                subprocess.run([decoder.settings.ffmpeg, '-nostdin', '-v', 'error', '-i', str(decoded),
                                '-af', effect, '-t', str(info['duration']), '-c:a', 'pcm_s16le', str(target)],
                               check=True, capture_output=True, timeout=60)
            with wave.open(str(target), 'rb') as audio:
                duration = audio.getnframes()/audio.getframerate()
            entry = {key: value for key, value in row.items() if key not in {'resolved_path', 'review', 'reference_original'}}
            entry.update(id=f'{row["id"]}-{variant}', path=target.name,
                         sha256=hashlib.sha256(target.read_bytes()).hexdigest(), duration=duration,
                         reference='\n'.join([row['reference']]*repeats),
                         group_id=row.get('group_id') or f'stress-source-{row["id"]}',
                         conditions=dict(synthetic=True, robustness_variant=variant,
                                         degraded_recording=variant in {'noise', 'telephone', 'reverb'},
                                         repetition=repeats > 1, long_form=duration >= 120),
                         source_id=row['id'], source_sha256=row['sha256'],
                         transformation=dict(variant=variant, seed=seed, repeats=repeats),
                         reference_status='Inherited diagnostic reference; human review required after transformation')
            generated.append(entry)
    target = output/'manifest.jsonl'
    target.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in generated), encoding='utf-8')
    return dict(clips=len(generated), manifest=str(target), synthetic=True,
                note='Repeated recordings test duration and repetition, not complete-song coverage. '
                     'These transformations do not establish real accompaniment or duet coverage.')


def report(paths):
    reports = [json.loads(path.read_text(encoding='utf-8')) for path in paths]
    if not reports or any(not data.get('per_clip') for data in reports):
        raise ValueError('At least one nonempty evaluation report is required')
    for path in paths[1:]:
        compare(paths[0], path)
    by_variant = {}
    for index, data in enumerate(reports):
        for row in data['per_clip']:
            variant = conditions(row).get('robustness_variant')
            labels = [variant] if variant else [key for key in CONDITIONS if
                      (row['language_switching'] if key == 'language_switching' else conditions(row).get(key) is True)]
            for label in labels or ['unclassified']:
                by_variant.setdefault((label, row['pipeline']), {}).setdefault(index, []).append(row)
    result = []
    for (variant, pipeline), groups in sorted(by_variant.items()):
        shared = set.intersection(*({r['id'] for r in group if r['state'] == 'completed'} for group in groups.values()))
        cells = []
        for index, group in groups.items():
            paired = [r for r in group if r['id'] in shared]
            denominator = sum(r['metrics']['reference_characters'] for r in paired)
            cells.append(dict(report=index, attempted=len(group), completed=sum(r['state']=='completed' for r in group),
                              paired_clips=len(paired), reference_characters=denominator,
                              micro_cer=sum(r['metrics']['character_errors'] for r in paired)/denominator if denominator else None,
                              empty_reference_insertions=sum(r['metrics'].get('empty_reference_insertions', 0) for r in paired),
                              recognition_seconds=sum(r['stage_seconds']['recognition'] for r in paired)
                              if paired and all('recognition' in r.get('stage_seconds', {}) for r in paired) else None))
        result.append(dict(variant=variant, pipeline=pipeline, models=cells))
    return dict(synthetic_diagnostic=all(conditions(r).get('synthetic') for data in reports for r in data['per_clip']),
                models=[{key: data['per_clip'][0].get(key) for key in ('model', 'revision', 'settings', 'inference_device', 'compute_type')}
                        for data in reports],
                per_condition=result,
                interpretation='CER uses the same completed clips in every compared model. '
                               'Synthetic stress results supplement reviewed real-recording evaluation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('audit')
    p.add_argument('manifest', type=Path)
    p.add_argument('--minimum', type=int, default=2)
    p.add_argument('--require-ready', action='store_true')
    p.add_argument('--output', type=Path)
    p = sub.add_parser('stress')
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--ids', nargs='+', required=True)
    p.add_argument('--variants', nargs='+', choices=VARIANTS, default=list(VARIANTS))
    p = sub.add_parser('report')
    p.add_argument('reports', type=Path, nargs='+')
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            result = audit(args.manifest, args.minimum)
        elif args.command == 'stress':
            result = stress(args.manifest, args.output, args.ids, args.variants)
        else:
            result = report(args.reports)
        if getattr(args, 'output', None) and args.command != 'stress':
            with args.output.open('x', encoding='utf-8') as output:
                json.dump(result, output, indent=2)
        print(json.dumps(result, indent=2))
        if getattr(args, 'require_ready', False) and not result['ready_for_representative_comparison']:
            raise SystemExit(1)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
