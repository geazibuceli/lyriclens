"""Summarize paired execution and review signals without lyric accuracy scores."""
import argparse
import hashlib
import json
import unicodedata
from pathlib import Path


def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def review_signals(segments):
    return dict(
        passages=len(segments),
        long_passages=sum(segment['end'] - segment['start'] > 20 for segment in segments),
        adjacent_duplicate_passages=sum(
            bool(segment['text'].strip()) and segment['text'].strip() == previous['text'].strip()
            for previous, segment in zip(segments, segments[1:])),
        empty_passages=sum(not segment['text'].strip() for segment in segments),
    )


def summarize(source):
    report = json.loads(source.read_text(encoding='utf-8'))
    if set(report.get('pipelines', [])) != {'direct', 'vocals'}:
        raise ValueError('Both direct and vocals pipelines are required')
    pairs = {}
    for run in report['per_run']:
        key = (run['id'], run['profile'])
        pair = pairs.setdefault(key, {})
        if run['pipeline'] in pair:
            raise ValueError('Duplicate pipeline run')
        pair[run['pipeline']] = run
    comparisons = []
    for (identifier, profile), pair in pairs.items():
        if set(pair) != {'direct', 'vocals'}:
            raise ValueError('Missing paired route')
        direct, vocals = pair['direct'], pair['vocals']
        for field in ('audio_sha256', 'duration', 'group_id', 'model', 'revision',
                      'settings', 'device', 'compute_type', 'language_mode'):
            if direct.get(field) != vocals.get(field):
                raise ValueError(f'Unpaired inputs/settings: {field}')
        item = dict(id=identifier, profile=profile, title=direct['title'],
                    completed_pair=all(run['state'] == 'completed' for run in pair.values()))
        texts = {}
        for pipeline, run in pair.items():
            cell = dict(state=run['state'], recognition_seconds=run['seconds'])
            if run['state'] == 'completed':
                stem = hashlib.sha256(identifier.encode()).hexdigest()[:16]
                raw_path = source.parent / f'{stem}-{profile}-{pipeline}.json'
                raw = json.loads(raw_path.read_text(encoding='utf-8'))
                cell['review_signals'] = review_signals(raw['segments'])
                texts[pipeline] = normalize(' '.join(s['text'] for s in raw['segments']))
            else:
                cell['error'] = run.get('error')
            item[pipeline] = cell
        item['same_normalized_text'] = texts.get('direct') == texts.get('vocals') if len(texts) == 2 else None
        comparisons.append(item)
    return dict(
        **report, paired_comparisons=comparisons,
        review_signal_interpretation='Long passages exceed 20 seconds. Adjacent duplicate passages repeat the same '
                                    'trimmed text. These are review prompts, not word accuracy or confidence. '
                                    'Real choruses may repeat; different segmentation affects these counts. '
                                    'Different route text does not identify which route is correct.',
        conclusion='No automatic winner. Listen and review the words before making an accuracy claim. '
                   'A small development pilot without verified accent labels and reviewed references '
                   'cannot establish robustness to different accents.',
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = summarize(args.summary)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
