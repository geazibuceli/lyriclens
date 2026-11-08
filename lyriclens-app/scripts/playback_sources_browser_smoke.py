"""Exercise source switching and automatic WAV recovery with owned demo audio."""
import json
import os
import wave
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, expect


def main():
    root = Path(__file__).resolve().parents[1]
    audio_file = root / 'frontend/public/demo/voice.wav'
    with wave.open(str(audio_file), 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
    result = dict(state='completed', original=[dict(start=0, end=duration, text='Owned demo fixture')],
                  edited=None, seconds=1)
    job = dict(id='playback-fixture', filename='fixture.mp3', title='Playback fixture',
               state='completed', stage='Finished', requested_language='en',
               results={'direct': result, 'vocals': result}, translations={},
               audio={'duration': duration}, pipelines=['direct', 'vocals'],
               created_at='2026-11-08T00:00:00Z')
    calls = []
    fail = {'wav': False, 'original': True}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def route(request):
            url = urlparse(request.request.url)
            if url.path.endswith('/audio'):
                query = parse_qs(url.query)
                calls.append(url.query)
                if not query and fail['original']:
                    return request.fulfill(body=b'Invalid MP3 fixture', content_type='audio/mpeg')
                if fail['wav']:
                    return request.abort('failed')
                data = audio_file.read_bytes()
                headers = {'Accept-Ranges': 'bytes'}
                requested = request.request.headers.get('range')
                if requested:
                    start, end = requested.removeprefix('bytes=').split('-', 1)
                    start, end = int(start or 0), int(end) if end else len(data) - 1
                    headers['Content-Range'] = f'bytes {start}-{end}/{len(data)}'
                    return request.fulfill(status=206, body=data[start:end + 1], headers=headers, content_type='audio/wav')
                return request.fulfill(body=data, headers=headers, content_type='audio/wav')
            if url.path == '/api/jobs':
                return request.fulfill(json=[job])
            if url.path == '/api/models':
                return request.fulfill(json={'prepared': True, 'profiles': [], 'languages': {'en': 'English'}})
            if url.path.endswith('/diagnostics'):
                return request.fulfill(json={'checks': []})
            return request.fulfill(json={})

        page.route('**/api/**', route)
        base = os.environ.get('LYRICLENS_BROWSER_URL', 'http://127.0.0.1:5181')
        page.goto(base + '/?job=playback-fixture')
        player = page.locator('.review-playback audio')
        page.wait_for_function("document.querySelector('.review-playback audio')?.currentSrc.includes('compatible=true') && document.querySelector('.review-playback audio').readyState >= 2")
        assert calls[:2] == ['', 'compatible=true']
        expect(page.locator('.review-playback [role=alert]')).to_have_count(0)
        page.get_by_label('Playback speed', exact=True).select_option('0.75')
        player.evaluate('async a => {a.currentTime=2; await a.play()}')
        page.get_by_label('Audio source', exact=True).select_option('vocals')
        page.wait_for_function("document.querySelector('.review-playback audio').currentSrc.includes('pipeline=vocals') && !document.querySelector('.review-playback audio').paused")
        state = player.evaluate('a => ({time:a.currentTime,speed:a.playbackRate})')
        assert 1.9 <= state['time'] < 3, state
        assert state['speed'] == .75
        player.evaluate('a => {a.pause(); a.currentTime=4}')
        page.get_by_label('Audio source', exact=True).select_option('direct')
        page.wait_for_function("document.querySelector('.review-playback audio').currentSrc.includes('compatible=true') && document.querySelector('.review-playback audio').readyState >= 2")
        state = player.evaluate('a => ({time:a.currentTime,paused:a.paused})')
        assert 3.9 <= state['time'] < 4.2 and state['paused'], state
        # Both sources fail: stop after one recovery, show a visible final error.
        fail['wav'] = True
        calls.clear()
        page.reload()
        expect(page.locator('.review-playback [role=alert]')).to_contain_text('Compatible WAV audio could not be loaded')
        page.wait_for_timeout(200)
        assert calls == ['', 'compatible=true'], calls
        # Recover a failure during playback without losing the listening position.
        fail.update(wav=False, original=False)
        page.reload()
        page.wait_for_function("document.querySelector('.review-playback audio')?.readyState >= 2")
        player.evaluate('async a => {a.currentTime=3; await a.play()}')
        player.evaluate("a => a.dispatchEvent(new Event('error'))")
        page.wait_for_function("document.querySelector('.review-playback audio').currentSrc.includes('compatible=true') && !document.querySelector('.review-playback audio').paused")
        assert 2.9 <= player.evaluate('a => a.currentTime') < 4
        assert not errors, errors
        browser.close()
    print(json.dumps({'automatic_fallback': True, 'source_position_and_play_state': True,
                      'speed_preserved': True, 'no_retry_loop': True, 'javascript_errors': 0}))


if __name__ == '__main__':
    main()
