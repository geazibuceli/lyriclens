"""Exercise the listening studio without inference; record the interactive demo."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'artifacts' / 'studio'
    output.mkdir(parents=True, exist_ok=True)
    media = Path(os.environ.get('LYRICLENS_STUDIO_MEDIA_DIR', str(root / 'docs/images')))
    media.mkdir(parents=True, exist_ok=True)
    fixture = json.loads((root / 'frontend/public/demo/transcript.json').read_text())
    base = os.environ.get('LYRICLENS_BROWSER_URL', 'http://127.0.0.1:5181')
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                      record_video_dir=str(output), accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Empty local workspace, with no installed models or backend needed.
        page.route('**/api/**', lambda route: route.fulfill(json=(
            [] if route.request.url.endswith('/jobs') else
            {'checks': [], 'note': 'Deterministic browser fixture'} if route.request.url.endswith('/diagnostics') else {})))
        page.goto(base)
        page.get_by_role('button', name='Open interactive demo', exact=True).click()
        demo = page.locator('.demo-editor')
        player = demo.locator('audio')
        player.evaluate('(a) => a.load()')
        expect(player).to_have_js_property('readyState', 4)
        demo.get_by_role('button', name='Follow lyrics', exact=True).click()
        player.evaluate('(a) => a.play()')
        page.wait_for_timeout(1200)
        player.evaluate('(a) => a.pause()')
        player.evaluate('(a) => { a.currentTime = 1; a.dispatchEvent(new Event("timeupdate")); }')
        expect(demo.locator('.lyric-current')).to_have_text(fixture[0]['text'])
        demo.get_by_label('Line 1', exact=True).fill('Every word belongs in time.')
        expect(demo.locator('.lyric-current')).to_have_text('Every word belongs in time.')
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=str(media / 'listening-studio.png'))
        demo.get_by_text('Tap to synchronize', exact=True).click()
        player.evaluate('(a) => { a.currentTime = 0.5; }')
        demo.get_by_role('button', name='Mark start now', exact=True).click()
        expect(demo.get_by_label('Next line')).to_have_value('1')
        with page.expect_download() as download:
            demo.get_by_role('button', name='Export demo LRC', exact=True).click()
        text = Path(download.value.path()).read_text(encoding='utf-8')
        assert '[00:00.50]Every word belongs in time.' in text, text
        demo.get_by_role('button', name='Reset example', exact=True).click()
        expect(demo.get_by_label('Line 1', exact=True)).to_have_value(fixture[0]['text'])
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
        video = page.video
        context.close()
        video.save_as(str(media / 'studio-demo.webm'))

        # Exercise a real editor component against a deterministic API fixture.
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        job = dict(id='studio-fixture', filename='studio.wav', title='Studio review', state='completed',
                   stage='completed', requested_language='en', created_at='2026-10-26T12:00:00Z',
                   audio={'duration': fixture[-1]['end']}, pipelines=['direct'],
                   results={'direct': dict(state='completed', original=fixture, edited=None, seconds=0)})

        def api(route):
            url = route.request.url
            if url.endswith('/audio'):
                route.fulfill(path=str(root / 'frontend/public/demo/voice.wav'), content_type='audio/wav')
            elif url.endswith('/jobs'):
                route.fulfill(json=[job])
            elif url.endswith('/models'):
                route.fulfill(json={'prepared': False, 'profiles': [], 'languages': {'en': 'English'}})
            elif url.endswith('/diagnostics'):
                route.fulfill(json={'checks': [], 'note': 'Deterministic browser fixture'})
            elif url.endswith('/edit'):
                job['results']['direct']['edited'] = route.request.post_data_json['segments']
                route.fulfill(json=job)
            else:
                route.fulfill(json={})
        page.route('**/api/**', api)
        page.goto(base + '/?job=studio-fixture')
        editor = page.locator('.transcript').first
        editor.get_by_label('Segment 1 transcript', exact=True).wait_for()
        page.locator('.review-playback audio').evaluate('(a) => { a.currentTime = 1; a.dispatchEvent(new Event("timeupdate")); }')
        expect(editor.locator('.segment-active')).to_have_count(1)
        editor.get_by_text('Import lyrics (TXT / LRC)', exact=True).click()
        editor.get_by_label('Lyrics text', exact=True).fill('\n'.join(s['text'] for s in fixture))
        editor.get_by_label('Import timing', exact=True).select_option('align')
        editor.get_by_role('button', name='Apply imported lyrics', exact=True).click()
        saved_text = fixture[0]['text'] + '!'
        editor.get_by_label('Segment 1 transcript', exact=True).fill(saved_text)
        editor.get_by_role('button', name='Save edits', exact=True).click()
        expect(editor.get_by_role('button', name='Saved', exact=True)).to_be_visible()
        editor.get_by_role('button', name='Follow lyrics', exact=True).click()
        expect(editor.locator('.lyric-current')).to_have_text(saved_text)
        editor.get_by_label('Segment 1 transcript', exact=True).fill('An unsaved correction')
        expect(editor.locator('.lyric-current')).to_have_text('An unsaved correction')
        editor.get_by_role('button', name='Undo transcript edit', exact=True).click()
        expect(editor.locator('.lyric-current')).to_have_text(saved_text)
        assert not errors, errors
        browser.close()
    print('Studio checks passed: demo, LRC, timing, mobile, highlighting, import, save, draft and undo.')


if __name__ == '__main__':
    main()
