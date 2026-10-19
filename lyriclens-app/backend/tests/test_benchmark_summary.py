import json
import pytest
from lyriclens.benchmark_summary import summarize


def reports(tmp_path):
    paths = [tmp_path/'small.json', tmp_path/'large.json']
    for path, model in zip(paths, ('small', 'large-v3')):
        rows = []
        for identifier, count in [('one', 10), ('two', 30)]:
            for pipeline in ('direct', 'vocals'):
                rows.append(dict(id=identifier, pipeline=pipeline, language='pt', sha256=identifier,
                                 reference='PRIVATE LYRIC', hypothesis='PRIVATE HYPOTHESIS',
                                 raw={'private': 'PRIVATE RAW'}, conditions={'singing': True},
                                 language_switching=False, split='development', duration=2,
                                 model=f'Systran/faster-whisper-{model}', state='completed', seconds=4,
                                 stage_seconds={'decode': 1, 'recognition': 3},
                                 metrics={'character_errors': 2, 'reference_characters': count,
                                          'word_errors': 1, 'reference_words': 2, 'cer': 2/count}))
        path.write_text(json.dumps(dict(split='development', language_mode='manual', per_clip=rows)), encoding='utf-8')
    return paths


def edit(path, mutate):
    report = json.loads(path.read_text(encoding='utf-8'))
    mutate(report)
    path.write_text(json.dumps(report), encoding='utf-8')


def test_summary_uses_micro_counts_and_never_exports_text(tmp_path):
    result = summarize(*reports(tmp_path))
    for cell in result['overall']['combinations'].values():
        assert cell['micro_cer'] == .1
        assert cell['micro_wer'] == .5
        assert cell['real_time_factor'] == 2
        assert cell['stage_seconds'] == {'decode': 2, 'recognition': 6}
    assert 'PRIVATE' not in json.dumps(result)
    assert result['per_language']['ja']['paired_clips'] == 0
    assert not result['human_review_required']


def test_summary_uses_same_cohort_for_all_four_cells_and_counts_failures(tmp_path):
    small, large = reports(tmp_path)
    edit(small, lambda report: report['per_clip'][3].update(state='failed', metrics={}))
    result = summarize(small, large)['overall']
    assert result['clips'] == 2 and result['paired_clips'] == 1
    for cell in result['combinations'].values():
        assert cell['reference_characters'] == 10
        assert cell['micro_cer'] == .2
        assert cell['total_seconds'] == 4
    assert result['combinations']['small/vocals']['failures'] == 1
    assert result['combinations']['large_v3/vocals']['failures'] == 0


def test_summary_with_no_shared_success_has_no_accuracy_score(tmp_path):
    small, large = reports(tmp_path)
    def fail(report):
        for row in report['per_clip']:
            row.update(state='failed', metrics={})
    edit(small, fail)
    result = summarize(small, large)['overall']
    assert result['paired_clips'] == 0
    for cell in result['combinations'].values():
        assert cell['micro_cer'] is None and cell['micro_wer'] is None
        assert cell['real_time_factor'] is None
        assert cell['stage_seconds'] == {}


@pytest.mark.parametrize('change', ['reference', 'missing', 'duration', 'mode', 'model'])
def test_summary_rejects_unpaired_or_mislabeled_runs(tmp_path, change):
    small, large = reports(tmp_path)
    def mutate(report):
        if change == 'reference':
            report['per_clip'][0]['reference'] = 'changed'
        elif change == 'missing':
            report['per_clip'].pop()
        elif change == 'duration':
            report['per_clip'][0]['duration'] = 3
        elif change == 'mode':
            report['language_mode'] = 'auto'
        else:
            report['per_clip'][0]['model'] = 'another-model'
    edit(large, mutate)
    with pytest.raises(ValueError):
        summarize(small, large)
