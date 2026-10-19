"""Exercise comparison and multilingual UI using an owned silence fixture."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'artifacts/browser-multilingual'
    output.mkdir(parents=True, exist_ok=True)
    # Four seconds of mono 16 kHz PCM, with a minimal WAV header.
    import io
    import wave
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(bytes(128000))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        base = 'http://127.0.0.1:5181'
        ids = []
        def wait(identifier):
            for _ in range(300):
                job = page.request.get(base+'/api/jobs/'+identifier).json()
                if job['state'] not in ('queued', 'processing'):
                    return job
                time.sleep(.1)
            raise AssertionError('Job did not finish')
        try:
            response = page.request.post(base+'/api/jobs', multipart={
                'file': {'name': 'multilingual-ui-check.wav', 'mimeType': 'audio/wav', 'buffer': buffer.getvalue()},
                'language': 'en', 'pipeline': 'both'})
            assert response.status == 202, response.text()
            identifier = response.json()['id']
            ids.append(identifier)
            job = wait(identifier)
            assert set(job['results']) == {'direct', 'vocals'}, job['pipelines']
            path = base+'/api/jobs/'+identifier
            for pipeline, word in [('direct', 'bright'), ('vocals', 'dark')]:
                response = page.request.put(path+'/edit', data={'pipeline': pipeline, 'segments': [
                    dict(start=.1, end=1.8, text='Hello '+word+' world', language='en'),
                    dict(start=2, end=3.9, text='Bonjour', language='fr')]})
                assert response.status == 200, response.text()
            page.goto(base+'/?job='+identifier)
            comparison = page.locator('.transcript-comparison')
            comparison.wait_for()
            assert '1 passage differs' in comparison.inner_text()
            assert comparison.locator('mark').all_text_contents() == ['bright', 'dark']
            assert comparison.locator('.comparison-passage').count() == 1
            comparison.get_by_label('Show only differences').uncheck()
            assert comparison.locator('.comparison-passage').count() == 2
            direct = page.locator('.transcript').first
            assert direct.get_by_label('Segment 1 language', exact=True).input_value() == 'en'
            assert direct.get_by_label('Segment 2 language', exact=True).input_value() == 'fr'
            direct.locator('.translation-panel summary').click()
            direct.get_by_label('Translation target language', exact=True).select_option('en')
            assert direct.get_by_role('button', name='Translate saved text', exact=True).is_enabled()
            for width, height in [(1440, 1000), (390, 844)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output/f'multilingual-{width}.png'), full_page=True)
            page.add_script_tag(path=str(root/'frontend/node_modules/axe-core/axe.min.js'))
            audit = page.evaluate("async () => await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
            (output/'accessibility.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
            assert not audit['violations'], [(v['id'], v['help']) for v in audit['violations']]
            direct.get_by_role('button', name='Retranscribe saved multilingual passages', exact=True).click()
            page.wait_for_url(lambda url: 'job=' in url and identifier not in url)
            child_id = page.url.split('job=')[1].split('&')[0]
            ids.append(child_id)
            child = wait(child_id)
            assert child['state'] == 'completed'
            assert [s['language'] for s in child['language_plan']] == ['en', 'fr']
            assert child['source_job_id'] == identifier
            assert not errors, errors
            print('Passed: saved transcript marks, matching filter, segment languages, mixed target selection, responsive layout, axe, and separate multilingual job. Silence fixture; no recognition quality claim.')
        finally:
            page.close()
            context = browser.new_context()
            for identifier in reversed(ids):
                assert context.request.delete(base+'/api/jobs/'+identifier).status == 204
            browser.close()


if __name__ == '__main__':
    main()
