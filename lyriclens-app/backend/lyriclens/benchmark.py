"""Prepare human review queues, export checked manifests and compare paired runs.

No command generates reference lyrics or downloads recordings.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .config import LANGUAGES
from .evaluate import load_manifest
from .profiles import PROFILE_IDS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def annotation(row):
    return {k: v for k, v in row.items() if k not in {'review', 'resolved_path'}}


def checked(row):
    review = row.get('review', {})
    return (review.get('status') == 'verified' and bool(review.get('reviewer', '').strip())
            and review.get('listened') is True and review.get('text_permission_checked') is True
            and review.get('annotation_sha256') == digest(annotation(row)))


def prepare(manifest, output):
    if output.exists():
        raise ValueError('Review queue already exists; refusing to overwrite annotations')
    rows = load_manifest(manifest)
    clips = []
    for row in rows:
        item = annotation(row)
        item['path'] = str(row['resolved_path'])
        item['group_id'] = ''
        item['review'] = {'status': 'pending', 'reviewer': '', 'listened': False,
                          'text_permission_checked': False}
        clips.append(item)
    output.write_text(json.dumps({'version': 1, 'clips': clips}, ensure_ascii=False, indent=2), encoding='utf-8')


def read_queue(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('clips'), list):
        raise ValueError('Unsupported review queue')
    return data


def status(path):
    rows = read_queue(path)['clips']
    return dict(clips=len(rows), verified=sum(checked(row) for row in rows),
                pending_ids=[row['id'] for row in rows if not checked(row)],
                missing_group_ids=[row['id'] for row in rows if not row.get('group_id', '').strip()],
                coverage={lang: dict(total=sum(r['language'] == lang for r in rows),
                                     verified=sum(r['language'] == lang and checked(r) for r in rows))
                          for lang in LANGUAGES},
                final_clips=sum(r['split'] == 'final' for r in rows))


def approve(path, identifier, reviewer):
    if not reviewer.strip():
        raise ValueError('Reviewer identity is required')
    data = read_queue(path)
    matches = [r for r in data['clips'] if r['id'] == identifier]
    if len(matches) != 1:
        raise ValueError('Select exactly one existing clip ID')
    row = matches[0]
    if not row.get('group_id', '').strip():
        raise ValueError('Set group_id to the song/recording/singer-session group before verification')
    if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() != row['sha256']:
        raise ValueError('Audio changed since preparation')
    from datetime import datetime, timezone
    row['review'] = dict(status='verified', reviewer=reviewer.strip(), listened=True,
                         text_permission_checked=True, annotation_sha256=digest(annotation(row)),
                         reviewed_at=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def export(path, output):
    if output.exists():
        raise ValueError('Manifest already exists; use a new versioned output name')
    rows = read_queue(path)['clips']
    if not rows or not all(checked(r) for r in rows):
        raise ValueError('Every clip must have a current human review; changed annotations need re-review')
    groups, hashes, ids = {}, {}, set()
    for row in rows:
        if row['id'] in ids or not row.get('group_id', '').strip():
            raise ValueError('Unique IDs and nonempty leakage groups are required')
        ids.add(row['id'])
        for mapping, key in [(groups, row['group_id']), (hashes, row['sha256'])]:
            if key in mapping and mapping[key] != row['split']:
                raise ValueError('Development/final leakage: shared audio or song/session group')
            mapping[key] = row['split']
    # Validate audio, language, duration and legacy manifest fields before writing.
    contents = ''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp)/'manifest.jsonl'
        candidate.write_text(contents, encoding='utf-8')
        load_manifest(candidate)
    output.write_text(contents, encoding='utf-8')
    return {'clips': len(rows), 'manifest_sha256': hashlib.sha256(contents.encode()).hexdigest(),
            'coverage': {split: {lang: sum(r['split'] == split and r['language'] == lang for r in rows)
                                 for lang in LANGUAGES} for split in ('development', 'final')}}


def compare(baseline, candidate):
    left, right = [json.loads(p.read_text(encoding='utf-8')) for p in (baseline, candidate)]
    if left.get('split') != right.get('split'):
        raise ValueError('Reports use different splits')
    def index(report):
        result = {}
        for row in report['per_clip']:
            key = (row['id'], row['pipeline'])
            if key in result:
                raise ValueError('Duplicate report row')
            result[key] = row
        return result
    a, b = index(left), index(right)
    if not a or a.keys() != b.keys():
        raise ValueError('Comparison requires the exact same clips and pipelines, including failures')
    pairs = []
    for key, old in a.items():
        new = b[key]
        for field in ('sha256', 'reference', 'language', 'conditions', 'language_switching', 'split'):
            if field not in old or old[field] != new.get(field):
                raise ValueError('Audio, references or conditions changed; reports are not paired')
        before, after = old.get('metrics', {}).get('cer'), new.get('metrics', {}).get('cer')
        pairs.append(dict(id=key[0], pipeline=key[1], language=old['language'],
                          baseline_state=old['state'], candidate_state=new['state'],
                          timing_recovery_attempted=bool(new.get('timing_recovery')),
                          timing_recovery_succeeded=bool((new.get('timing_recovery') or {}).get('succeeded')),
                          cer_delta=after-before if old['state'] == new['state'] == 'completed'
                          and before is not None and after is not None else None))
    return dict(split=left['split'], pairs=pairs,
                interpretation='Negative CER delta favors candidate. Failures remain visible. No automatic model selection or statistical significance claim.')


def plan(manifest, output, split, profiles, modes, device, compute, representative=False, minimum_groups=2):
    if output.exists():
        raise ValueError('Protocol already exists; refusing to overwrite')
    rows = load_manifest(manifest, require_reviewed=True)
    selected = [r for r in rows if r['split'] == split]
    if not selected:
        raise ValueError('No reviewed clips in this split')
    if split == 'final' and (len(profiles) != 1 or len(modes) != 1):
        raise ValueError('Choose one model and language mode on development data before final evaluation')
    if representative:
        from .quality import audit
        if not audit(manifest, minimum_groups)['ready_for_representative_comparison']:
            raise ValueError('Representative coverage is incomplete; run lyriclens.quality audit to inspect gaps')
    protocol = dict(version=1, manifest=str(manifest.resolve()),
                    manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), split=split,
                    profiles=profiles, language_modes=modes, device=device, compute=compute,
                    pipelines=['direct','vocals'],
                    coverage={lang: sum(r['language'] == lang for r in selected) for lang in LANGUAGES})
    if representative:
        protocol['representative_coverage'] = dict(minimum_independent_groups=minimum_groups)
    from .profiles import profile_settings
    from .config import Settings
    from dataclasses import replace
    protocol['models'] = {}
    for profile in profiles:
        settings = replace(profile_settings(Settings(), profile), device=device, compute_type=compute)
        protocol['models'][profile] = dict(model_id=settings.model_id, revision=settings.revision,
                                          settings=settings.inference(), separation_device=settings.separation_device)
    protocol['protocol_sha256'] = digest(protocol)
    output.write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    return protocol


def run(protocol_path):
    import subprocess
    import sys
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    signature = protocol.pop('protocol_sha256')
    if digest(protocol) != signature:
        raise ValueError('Protocol changed; prepare a new protocol explicitly')
    manifest = Path(protocol['manifest'])
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != protocol['manifest_sha256']:
        raise ValueError('Manifest changed after protocol freeze')
    load_manifest(manifest, require_reviewed=True)
    if protocol.get('representative_coverage'):
        from .quality import audit
        if not audit(manifest, protocol['representative_coverage']['minimum_independent_groups'])['ready_for_representative_comparison']:
            raise ValueError('Representative coverage no longer satisfies the frozen protocol')
    from .profiles import profile_settings
    from .config import Settings
    from dataclasses import replace
    for profile in protocol['profiles']:
        settings = replace(profile_settings(Settings(), profile), device=protocol['device'], compute_type=protocol['compute'])
        current = dict(model_id=settings.model_id, revision=settings.revision, settings=settings.inference(),
                       separation_device=settings.separation_device)
        if current != protocol['models'][profile]:
            raise ValueError('Model revision or inference configuration changed after protocol freeze')
    directory = protocol_path.with_suffix('.runs')
    directory.mkdir()  # Refuse to overwrite/repeat a previous protocol execution.
    results = []
    for profile in protocol['profiles']:
        for mode in protocol['language_modes']:
            output = directory/f'{profile}-{mode}.json'
            command = [sys.executable, '-m', 'lyriclens.evaluate', str(manifest), '--require-reviewed',
                       '--split', protocol['split'], '--model-profile', profile,
                       '--device', protocol['device'], '--compute', protocol['compute'], '--output', str(output)]
            if mode == 'manual':
                command.append('--manual-language')
            result = subprocess.run(command, check=False)
            results.append(dict(profile=profile, language_mode=mode, returncode=result.returncode, report=output.name))
            (directory/'runs.json').write_text(json.dumps(dict(protocol_sha256=signature, runs=results), indent=2), encoding='utf-8')
            if result.returncode:
                raise ValueError('Evaluation process failed; inspect runs.json and console output. No automatic retry.')
    for item in results[1:]:
        comparison = compare(directory/results[0]['report'], directory/item['report'])
        (directory/f"compare-{item['profile']}-{item['language_mode']}.json").write_text(
            json.dumps(comparison, indent=2), encoding='utf-8')
    print(f'Wrote {len(results)} runs to {directory}. Inspect failures before interpreting CER.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    p = sub.add_parser('plan', help='Freeze a reviewed manifest and model/configuration matrix without inference')
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--split', required=True, choices=['development','final'])
    p.add_argument('--profiles', nargs='+', choices=PROFILE_IDS, default=['configured','large-v3'])
    p.add_argument('--language-modes', nargs='+', choices=['auto','manual'], default=['auto'])
    p.add_argument('--device', choices=['cpu','cuda'], default='cpu')
    p.add_argument('--compute', default='int8')
    p.add_argument('--representative', action='store_true', help='Require reviewed real coverage for every language and condition in development and final splits')
    p.add_argument('--minimum-groups', type=int, default=2)
    p = sub.add_parser('run', help='Execute a frozen protocol with prepared local models, without downloading')
    p.add_argument('protocol', type=Path)
    p = sub.add_parser('verify', help='Human operator attests to listening and checking text permissions')
    p.add_argument('queue', type=Path)
    p.add_argument('id')
    p.add_argument('--reviewer', required=True)
    p.add_argument('--confirm-listened-and-text-permission', action='store_true', required=True)
    p = sub.add_parser('status')
    p.add_argument('queue', type=Path)
    p = sub.add_parser('export')
    p.add_argument('queue', type=Path)
    p.add_argument('output', type=Path)
    p = sub.add_parser('compare')
    p.add_argument('baseline', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('output', type=Path)
    p = sub.add_parser('summarize', help='Text-free Small/Large-v3 x direct/vocals summary on shared successful clips')
    p.add_argument('baseline', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.manifest, args.output)
            print('Review queue prepared; all references are pending human verification.')
        elif args.command == 'verify':
            approve(args.queue, args.id, args.reviewer)
            print('Human attestation recorded. Editing any annotation invalidates it.')
        elif args.command == 'status':
            print(json.dumps(status(args.queue), indent=2))
        elif args.command == 'export':
            print(json.dumps(export(args.queue, args.output), indent=2))
        elif args.command == 'plan':
            print(json.dumps(plan(args.manifest, args.output, args.split, args.profiles,
                                  args.language_modes, args.device, args.compute,
                                  args.representative, args.minimum_groups), indent=2))
        elif args.command == 'run':
            run(args.protocol)
        elif args.command == 'summarize':
            from .benchmark_summary import summarize
            result = summarize(args.baseline, args.candidate)
            with args.output.open('x', encoding='utf-8') as output:
                json.dump(result, output, indent=2)
            print(f'Wrote text-free four-way summary to {args.output}')
        else:
            if args.output.exists():
                raise ValueError('Comparison output already exists')
            args.output.write_text(json.dumps(compare(args.baseline, args.candidate), indent=2), encoding='utf-8')
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
