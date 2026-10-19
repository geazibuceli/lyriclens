"""Text-free four-way comparisons on a common set of successful recordings."""
import json
from .benchmark import compare
from .config import LANGUAGES


def summarize(baseline, candidate):
    # Reuse strict checks for changed references, hashes, conditions and split.
    compare(baseline, candidate)
    reports = [json.loads(path.read_text(encoding='utf-8')) for path in (baseline, candidate)]
    if reports[0].get('language_mode') != reports[1].get('language_mode'):
        raise ValueError('Four-way comparison requires the same language mode')
    cells = {}
    identifiers = None
    metadata = {}
    for label, report in zip(('small', 'large_v3'), reports):
        rows = report['per_clip']
        expected = 'Systran/faster-whisper-small' if label == 'small' else 'Systran/faster-whisper-large-v3'
        if any(row.get('model') != expected for row in rows):
            raise ValueError('Expected Small baseline and Large-v3 candidate, in that order')
        config_fields = ('model', 'revision', 'settings', 'inference_device', 'compute_type')
        if any(any(row.get(key) != rows[0].get(key) for key in config_fields) for row in rows):
            raise ValueError('Model configuration changed within a report')
        if {row['pipeline'] for row in rows} != {'direct', 'vocals'}:
            raise ValueError('Four-way summary requires both direct and vocals pipelines')
        for pipeline in ('direct', 'vocals'):
            index = {row['id']: row for row in rows if row['pipeline'] == pipeline}
            if identifiers is None:
                identifiers = set(index)
            if set(index) != identifiers:
                raise ValueError('All four combinations must contain the same clip IDs')
            for identifier, row in index.items():
                fields = ('sha256', 'reference', 'language', 'duration', 'conditions', 'language_switching', 'split')
                values = {key: row[key] for key in fields}
                if identifier in metadata and metadata[identifier] != values:
                    raise ValueError('Direct and vocals inputs are not paired')
                metadata[identifier] = values
            cells[f'{label}/{pipeline}'] = index
    shared = {identifier for identifier in identifiers
              if all(index[identifier]['state'] == 'completed' for index in cells.values())}

    def aggregate(ids):
        paired = shared & ids
        combinations = {}
        for name, index in cells.items():
            rows = [index[identifier] for identifier in sorted(paired)]
            characters = sum(row['metrics']['reference_characters'] for row in rows)
            words = sum(row['metrics'].get('reference_words', 0) for row in rows)
            duration = sum(row['duration'] for row in rows)
            stages = sorted({stage for row in rows for stage in row.get('stage_seconds', {})})
            combinations[name] = dict(
                attempted=len(ids), completed=sum(index[i]['state'] == 'completed' for i in ids),
                failures=sum(index[i]['state'] != 'completed' for i in ids),
                paired_clips=len(rows), reference_characters=characters,
                micro_cer=sum(row['metrics']['character_errors'] for row in rows)/characters if characters else None,
                micro_wer=sum(row['metrics'].get('word_errors', 0) for row in rows)/words if words else None,
                empty_reference_insertions=sum(row['metrics'].get('empty_reference_insertions', 0) for row in rows),
                total_seconds=sum(row['seconds'] for row in rows),
                real_time_factor=sum(row['seconds'] for row in rows)/duration if duration else None,
                stage_seconds={stage: sum(row['stage_seconds'][stage] for row in rows)
                               for stage in stages if all(stage in row.get('stage_seconds', {}) for row in rows)},
                max_sampled_rss_bytes=max((row['peak_memory_bytes'] for row in rows
                                          if row.get('peak_memory_bytes') is not None), default=None),
            )
        return dict(clips=len(ids), paired_clips=len(paired), combinations=combinations)

    return dict(
        split=reports[0]['split'],
        language_mode=reports[0].get('language_mode', 'not recorded'),
        human_review_required=all(report.get('human_review_required', False) for report in reports),
        interpretation='All accuracy and timing totals use only clips completed by all four combinations. '
                       'Failure counts cover every attempted clip. Development diagnostics do not establish final accuracy. '
                       'Timing includes cold initialization and model reuse; RSS excludes VRAM. No automatic model selection.',
        models={label: {key: report['per_clip'][0].get(key) for key in
                        ('model', 'revision', 'settings', 'inference_device', 'compute_type', 'environment')}
                for label, report in zip(('small', 'large_v3'), reports)},
        overall=aggregate(identifiers),
        per_language={language: aggregate({i for i in identifiers if metadata[i]['language'] == language})
                      for language in LANGUAGES},
    )
