"""Download three author-licensed complete songs for a local development pilot.

Run explicitly; never called by the application. Audio, publisher lyrics and HTML
evidence stay in the selected local directory. No human review is certified, no
lyrics are generated from model output, and no final evaluation set is created.
"""
import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from lyriclens.adapters import FFmpegDecoder
from lyriclens.benchmark import annotation
from lyriclens.config import Settings


SONGS = (
    ('IWillNotLetYouLetMeDown', 'I Will Not Let You Let Me Down'),
    ('ThisIsEverything', 'This Is Everything'),
    ('HollowGrove', 'Hollow Grove'),
)
LICENSE = 'https://creativecommons.org/licenses/by/4.0/'
FAQ = 'https://www.joshwoodward.com/faq'


class SongPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.schemas = []
        self.audio_urls = []
        self.capture = False
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.capture = True
            self.chunks = []
        if tag == 'audio' and attrs.get('src'):
            self.audio_urls.append(attrs['src'])

    def handle_data(self, data):
        if self.capture:
            self.chunks.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.capture:
            self.schemas.append(json.loads(''.join(self.chunks)))
            self.capture = False


def parse_song(html, title):
    page = SongPage()
    page.feed(html)
    matches = [item for item in page.schemas if isinstance(item, dict)
               and item.get('@type') == 'MusicRecording' and item.get('name') == title]
    if len(matches) != 1:
        raise ValueError(f'{title}: expected exactly one publisher recording record')
    song = matches[0]
    if song.get('license') != LICENSE or song.get('byArtist', {}).get('name') != 'Josh Woodward':
        raise ValueError(f'{title}: publisher identity or CC BY 4.0 declaration changed')
    lyrics = song.get('recordingOf', {}).get('lyrics', {}).get('text')
    if not isinstance(lyrics, str) or not lyrics.strip():
        raise ValueError(f'{title}: publisher lyrics are unavailable')
    urls = [url for url in page.audio_urls if urlparse(url).scheme == 'https'
            and urlparse(url).hostname == 'www.joshwoodward.com'
            and urlparse(url).path.startswith('/mp3/TheWake/')
            and urlparse(url).path.endswith('.mp3')
            and 'NoVox' not in url]
    if len(urls) != 1:
        raise ValueError(f'{title}: expected exactly one original vocal MP3')
    return urls[0], lyrics.replace('\r\n', '\n').strip()


def fetch(url, target, limit):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'LyricLensBenchmark/0.1 (explicit local development pilot)',
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f'Download exceeds {limit} bytes: {url}')
    with target.open('xb') as handle:
        handle.write(content)
    return dict(url=url, path=target.name, bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest())


def prepare(output):
    # A failed download leaves its evidence in place; choose a fresh version to retry.
    output.mkdir(parents=True, exist_ok=False)
    decoder = FFmpegDecoder(Settings())
    evidence = [fetch(FAQ, output / 'publisher-faq.html', 2_000_000)]
    rows, sources = [], []
    for slug, title in SONGS:
        identifier = 'woodward-' + slug.lower()
        url = 'https://www.joshwoodward.com/song/' + slug
        page = output / f'{identifier}.html'
        page_evidence = fetch(url, page, 2_000_000)
        audio_url, lyrics = parse_song(page.read_text(encoding='utf-8'), title)
        original = output / f'{identifier}.mp3'
        audio_evidence = fetch(audio_url, original, 25_000_000)
        audio = output / f'{identifier}.wav'
        decoded = decoder.decode(original, audio)
        if not 120 <= decoded['duration'] <= 600:
            raise ValueError(f'{title}: unexpected full-song duration')
        reference = output / f'{identifier}-publisher-lyrics.txt'
        reference.write_text(lyrics + '\n', encoding='utf-8')
        credit = f'"{title}" by Josh Woodward. https://www.joshwoodward.com/ — CC BY 4.0 ({LICENSE}).'
        row = dict(
            id=identifier, title=title, path=audio.name,
            sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
            language='en', split='development', duration=decoded['duration'],
            # Conservatively keep this artist/album session in one group.
            group_id='josh-woodward-the-wake-2012',
            reference=lyrics, reference_source=url + ' (publisher structured lyric field)',
            permissions=credit, source_license='CC-BY-4.0', source_url=url,
            conditions={'full_song': True, 'synthetic': False}, language_switching=False,
            reference_status='Publisher text only; expand chorus/repeat shorthand against the recording during human review.',
            condition_status='Complete source track retained. Other listening conditions and language switching need human confirmation.',
            review={'status': 'pending', 'reviewer': '', 'listened': False,
                    'text_permission_checked': False},
            preparation={'audio_change': 'Complete MP3 decoded to mono PCM16 WAV at 16 kHz; no cuts or silence removal',
                         'reference_change': 'CRLF normalized to LF; surrounding whitespace removed; no repetition expansion'},
        )
        rows.append(row)
        evidence.extend([page_evidence, audio_evidence])
        sources.append(dict(id=identifier, title=title, source_url=url, audio_url=audio_url,
                            license='CC-BY-4.0', license_url=LICENSE, attribution=credit,
                            duration=decoded['duration'], audio_sha256=row['sha256'],
                            reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest()))
        print(f'Prepared {title}: {decoded["duration"]:.2f}s; reference review pending', flush=True)
    manifest = output / 'pending-manifest.jsonl'
    manifest.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    # Retain the source group while resetting every approval to pending.
    queue = {'version': 1, 'clips': [{**annotation(row), 'path': str((output / row['path']).resolve()),
                                    'review': row['review']} for row in rows]}
    (output / 'review.json').write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding='utf-8')
    provenance = dict(
        version=1, retrieved_at=datetime.now(timezone.utc).isoformat(),
        purpose='English full-song development pilot; not representative accuracy validation or training data approval',
        human_review_required=True, independent_groups=1, final_recordings=0,
        sources=sources, evidence=evidence,
    )
    (output / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'ATTRIBUTION.txt').write_text('\n'.join(source['attribution'] for source in sources) +
        '\nChanges: complete source MP3 decoded to mono PCM16 WAV at 16 kHz. Publisher lyric whitespace normalized.\n', encoding='utf-8')
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New local output directory (prefer ignored .runtime)')
    args = parser.parse_args()
    prepare(args.output.resolve())
