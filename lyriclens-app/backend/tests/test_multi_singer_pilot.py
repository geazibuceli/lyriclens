"""Diverse singers must not become invented accent labels or verified references."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def pilot(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('multi_singer', scripts / 'prepare_multi_singer_pilot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def page(title='On A Silent Night', upload_id='40172', uploader='Javolenus', license='by-nc/3.0'):
    return (f'<title>ccMixter - {title}</title><a rel="license" href="http://creativecommons.org/licenses/{license}/">License</a>'
            '<div style="overflow:scroll;height:19em">Description. Lyrics:<br>' +
            'Publisher fixture line.<br>' * 12 + '</div>' +
            f"<script>$('_ep_{upload_id}').href = 'https://ccmixter.org/content/{uploader}/recording.mp3'</script>")


def test_parses_track_specific_license_and_bounded_lyrics(pilot):
    url, description = pilot.parse_upload(page(), '40172', 'Javolenus',
        'https://creativecommons.org/licenses/by-nc/3.0/', 'On A Silent Night')
    assert url.endswith('/recording.mp3')
    assert pilot.extract_lyrics(description, 'Lyrics:').startswith('Publisher fixture line.')
    with pytest.raises(ValueError, match='license changed'):
        pilot.parse_upload(page(license='by-nc-nd/3.0'), '40172', 'Javolenus',
            'https://creativecommons.org/licenses/by-nc/3.0/', 'On A Silent Night')
    with pytest.raises(ValueError, match='origin'):
        pilot.parse_upload(page(uploader='other'), '40172', 'Javolenus',
            'https://creativecommons.org/licenses/by-nc/3.0/', 'On A Silent Night')


def test_rejects_missing_or_damaged_publisher_lyrics(pilot):
    for description in ('No lyrics here', 'Lyrics: short', 'Lyrics: ' + '\ufffd' * 150):
        with pytest.raises(ValueError):
            pilot.extract_lyrics(description, 'Lyrics:')


def test_legacy_punctuation_is_decoded_without_replacement(pilot, tmp_path):
    path = tmp_path / 'page.html'
    path.write_bytes(b'Please don\x92t fear me')
    text, encoding = pilot.read_page(path)
    assert text == 'Please don’t fear me'
    assert encoding == 'cp1252'


def test_prepares_two_singers_without_certifying_accents_or_text(pilot, tmp_path, monkeypatch):
    referers = []

    def fetch(url, target, limit, referer=None):
        referers.append(referer)
        if url.endswith('/27734'):
            data = page('[Rhiannon] Where You Are Now Acapella', '27734', 'ascension', 'by/3.0')
            data = data.replace('Description. Lyrics:', 'Description.<br>Please don')
        elif target.suffix == '.html':
            source = next(source for source in pilot.RECORDINGS if source['source_url'] == url)
            data = page(source['title'], source['upload_id'], source['uploader'])
        else:
            data = 'MP3 test fixture'
        target.write_text(data, encoding='utf-8')
        return {'url': url, 'path': target.name}

    class Decoder:
        def __init__(self, settings):
            pass

        def decode(self, source, target):
            target.write_bytes(b'PCM test fixture')
            return {'duration': 200}

    monkeypatch.setattr(pilot, 'fetch', fetch)
    monkeypatch.setattr(pilot, 'FFmpegDecoder', Decoder)
    output = tmp_path / 'pilot'
    provenance = pilot.prepare(output)
    assert provenance['singers'] == provenance['independent_groups'] == 2
    queue = json.loads((output / 'review.json').read_text(encoding='utf-8'))
    assert len({row['group_id'] for row in queue['clips']}) == 2
    for row in queue['clips']:
        assert row['review']['status'] == 'pending'
        assert row['review']['listened'] is False
        assert row['accent']['label'] is None
        assert row['training_allowed'] is False
        assert row['split'] == 'development'
    assert all(source['source_url'] in referers for source in pilot.RECORDINGS)
    assert 'Rhiannon' in (output / 'ATTRIBUTION.txt').read_text(encoding='utf-8')
    sheet = (output / 'pronunciation-review.csv').read_text(encoding='utf-8')
    assert 'accent_or_pronunciation_notes' in sheet
    assert 'Rhiannon Delpero' in sheet
    with pytest.raises(FileExistsError):
        pilot.prepare(output)
