import pytest
from lyriclens.experiments import screen


def row(variant, identifier, errors=2, state='completed', language='pt'):
    return dict(variant=variant, id=identifier, pipeline='direct', sha256=identifier,
                language=language, state=state,
                metrics=dict(reference_characters=10, character_errors=errors))


def test_recovered_clips_do_not_change_paired_accuracy():
    result = screen([row('baseline', 'one'), row('baseline', 'two', state='failed'),
                     row('candidate', 'one'), row('candidate', 'two', errors=9)])[0]
    group = result['groups'][0]
    assert group['paired_clips'] == 1
    assert group['baseline_cer'] == group['candidate_cer'] == .2
    assert group['recovered_clips'] == 1
    assert result['eligible_for_further_validation']


@pytest.mark.parametrize('regression', ['errors', 'failure'])
def test_any_language_regression_blocks_candidate(regression):
    result = screen([row('baseline', 'one'), row('candidate', 'one', errors=0),
                     row('baseline', 'two', language='en'),
                     row('candidate', 'two', errors=3 if regression == 'errors' else 0,
                         state='failed' if regression == 'failure' else 'completed', language='en')])[0]
    assert not result['eligible_for_further_validation']


def test_unpaired_inputs_or_denominators_are_rejected():
    with pytest.raises(ValueError):
        screen([row('baseline', 'one'), row('candidate', 'two')])
    changed = row('candidate', 'one')
    changed['metrics']['reference_characters'] = 11
    with pytest.raises(ValueError):
        screen([row('baseline', 'one'), changed])
