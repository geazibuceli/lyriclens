"""Prepare two additional singers from licensed uploads, with human review pending.

Explicit local research only. The recording licenses are noncommercial; neither
the music nor its lyrics are bundled with the MIT application or approved for
training. Singer identities come from upload credits; accents remain unassigned.
"""
import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from lyriclens.adapters import FFmpegDecoder
from lyriclens.benchmark import annotation
from lyriclens.config import Settings
from prepare_open_song_pilot import fetch


RECORDINGS = (
    dict(id='javolenus-on-a-silent-night', title='On A Silent Night', singer='Javolenus',
         uploader='Javolenus', upload_id='40172',
         source_url='https://ccmixter.org/files/Javolenus/40172',
         lyrics_url='https://ccmixter.org/files/Javolenus/40172',
         lyric_marker='Lyrics:', license='CC-BY-NC-3.0',
         credit='On A Silent Night by Javolenus; composition, lyrics and single-take performance credited to the uploader.'),
    dict(id='rhiannon-where-you-are-now', title='Where You Are Now', singer='Rhiannon Delpero',
         uploader='unreal_dm', upload_id='30304',
         source_url='https://ccmixter.org/files/unreal_dm/30304',
         lyrics_url='https://ccmixter.org/files/ascension/27734',
         lyric_marker='Please don', license='CC-BY-NC-3.0',
         credit='Where You Are Now remix by unreal_dm, featuring Ascension/WolfFly; vocals by Rhiannon Delpero (SizzleFly). '
                'Vocal/lyric source: Ascension, ccMixter upload 27734, CC BY 3.0.'),
)


class UploadPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.licenses, self.description = [], []
        self.depth = 0
        self.title = ''
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        if tag == 'a' and 'license' in attrs.get('rel', '').split():
            self.licenses.append(attrs.get('href', '').replace('http://', 'https://'))
        if tag == 'div':
            if self.depth:
                self.depth += 1
            elif 'overflow:scroll' in attrs.get('style', '').replace(' ', ''):
                self.depth = 1
        if self.depth and tag == 'br':
            self.description.append('\n')

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.depth:
            self.description.append(data)

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'div' and self.depth:
            self.depth -= 1


def parse_upload(html, upload_id, uploader, expected_license, title):
    page = UploadPage()
    page.feed(html)
    if page.title.strip() != 'ccMixter - ' + title or set(page.licenses) != {expected_license}:
        raise ValueError('Upload title or recording-specific license changed')
    matches = re.findall(r"\$\('_ep_" + re.escape(upload_id) + r"'\)\.href = '([^']+)'", html)
    if len(matches) != 1:
        raise ValueError('Expected exactly one public upload MP3')
    url = matches[0]
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'ccmixter.org' or not parsed.path.startswith('/content/' + uploader + '/') or not parsed.path.endswith('.mp3'):
        raise ValueError('Unexpected audio origin or format')
    return url, ''.join(page.description).strip()


def extract_lyrics(description, marker):
    if description.count(marker) != 1:
        raise ValueError('Expected a unique publisher lyric marker')
    before, after = description.split(marker, 1)
    lyrics = after if marker == 'Lyrics:' else marker + after
    lyrics = '\n'.join(line.strip() for line in lyrics.splitlines()).strip()
    if len(lyrics) < 100 or '\ufffd' in lyrics:
        raise ValueError('Publisher lyrics are missing or have decoding damage')
    return lyrics


def read_page(path):
    # ccHost pages may declare UTF-8 but contain legacy Windows-1252 punctuation.
    raw = path.read_bytes()
    try:
        return raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return raw.decode('cp1252'), 'cp1252'


def write_review_sheet(rows, target):
    fields = ('recording_id', 'singer', 'start_seconds', 'end_seconds',
              'publisher_text', 'words_sung', 'error_type',
              'accent_or_pronunciation_notes', 'reviewer')
    with target.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({'recording_id': row['id'], 'singer': row['singer']})


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    evidence, rows, sources = [], [], []
    decoder = FFmpegDecoder(Settings())
    license_url = 'https://creativecommons.org/licenses/by-nc/3.0/'
    for source in RECORDINGS:
        identifier = source['id']
        page = output / f'{identifier}-recording.html'
        evidence.append(fetch(source['source_url'], page, 2_000_000))
        html, encoding = read_page(page)
        audio_url, description = parse_upload(html, source['upload_id'], source['uploader'], license_url, source['title'])
        lyric_license = license_url
        if source['lyrics_url'] != source['source_url']:
            lyric_page = output / f'{identifier}-lyrics.html'
            evidence.append(fetch(source['lyrics_url'], lyric_page, 2_000_000))
            lyric_html, lyric_encoding = read_page(lyric_page)
            _, description = parse_upload(lyric_html, '27734', 'ascension',
                                          'https://creativecommons.org/licenses/by/3.0/',
                                          '[Rhiannon] Where You Are Now Acapella')
            lyric_license = 'https://creativecommons.org/licenses/by/3.0/'
        else:
            lyric_encoding = encoding
        lyrics = extract_lyrics(description, source['lyric_marker'])
        mp3, wav = output / f'{identifier}.mp3', output / f'{identifier}.wav'
        evidence.append(fetch(audio_url, mp3, 25_000_000, referer=source['source_url']))
        info = decoder.decode(mp3, wav)
        if not 120 <= info['duration'] <= 600:
            raise ValueError('Unexpected complete recording duration')
        (output / f'{identifier}-publisher-lyrics.txt').write_text(lyrics + '\n', encoding='utf-8')
        credit = source['credit'] + ' ' + source['source_url'] + ' CC BY-NC 3.0: ' + license_url
        row = dict(id=identifier, title=source['title'], singer=source['singer'],
                   group_id='singer-session-' + source['singer'].lower().replace(' ', '-'),
                   path=wav.name, sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),
                   language='en', split='development', duration=info['duration'],
                   reference=lyrics, reference_source=source['lyrics_url'], permissions=credit,
                   source_license=source['license'], source_url=source['source_url'],
                   conditions={'full_song': True, 'synthetic': False}, language_switching=False,
                   accent={'status': 'pending', 'label': None, 'basis': 'No accent inferred from name or location'},
                   reference_status='Publisher text; repetitions, transcription and remix correspondence need listening review.',
                   condition_status='Complete uploaded MP3 retained; listening labels and language switching pending.',
                   training_allowed=False, research_only=True,
                   review={'status': 'pending', 'reviewer': '', 'listened': False, 'text_permission_checked': False})
        rows.append(row)
        sources.append({**source, 'audio_url': audio_url, 'duration': info['duration'],
                        'audio_sha256': row['sha256'], 'license_url': license_url,
                        'lyric_license_url': lyric_license,
                        'recording_page_encoding': encoding, 'lyric_page_encoding': lyric_encoding})
        print(f"Prepared {source['singer']}: {info['duration']:.2f}s; review pending", flush=True)
    (output / 'pending-manifest.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    queue = {'version': 1, 'clips': [{**annotation(row), 'path': str((output / row['path']).resolve()),
                                    'review': row['review']} for row in rows]}
    (output / 'review.json').write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding='utf-8')
    write_review_sheet(rows, output / 'pronunciation-review.csv')
    provenance = dict(retrieved_at=datetime.now(timezone.utc).isoformat(), singers=2, independent_groups=2,
                      human_review_required=True, accent_labels_verified=False, training_allowed=False,
                      sources=sources, evidence=evidence,
                      changes='Complete MP3 decoded to mono PCM16 WAV at 16 kHz. HTML lyric markup stripped; line whitespace normalized. No reference generated from ASR.')
    (output / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'ATTRIBUTION.txt').write_text('\n\n'.join(row['permissions'] + '\nLyrics: ' + row['reference_source'] for row in rows) +
                                            '\n\n' + provenance['changes'] + '\nLocal noncommercial evaluation only.\n', encoding='utf-8')
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New local research directory')
    args = parser.parse_args()
    prepare(args.output.resolve())
