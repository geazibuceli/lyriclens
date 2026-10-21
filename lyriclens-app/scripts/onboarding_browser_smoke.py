"""Check the default upload flow using owned silence and mocked model readiness."""
import io
import json
import os
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    base = os.environ.get('LYRICLENS_BROWSER_URL', 'http://127.0.0.1:5181')
    output = Path(__file__).resolve().parents[1]/'artifacts/browser-onboarding'
    output.mkdir(parents=True, exist_ok=True)
    data = io.BytesIO()
    with wave.open(data, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(bytes(128000))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def readiness(route):
            # This smoke checks UI interaction, not checkpoint installation.
            response = route.fetch()
            models = response.json()
            models['prepared'] = True
            for profile in models['profiles']:
                profile['prepared'] = True
            route.fulfill(response=response, json=models)

        page.route('**/api/models', readiness)
        page.goto(base)
        page.get_by_role('heading', name='Drop a little music here').wait_for()
        assert page.get_by_label('Audio language').is_visible()
        assert not page.get_by_label('Recognition model').is_visible()
        assert not page.get_by_label('Listening mode').is_visible()
        page.screenshot(path=str(output/'upload-desktop.png'))
        page.get_by_text('Advanced transcription options', exact=True).click()
        page.get_by_label('Recognition model').select_option('aligned')
        assert page.get_by_label('Listening mode').input_value() == 'direct'
        page.get_by_text('Advanced transcription options', exact=True).click()
        page.get_by_label('Upload music clip').set_input_files(
            dict(name='onboarding-silence.wav', mimeType='audio/wav', buffer=data.getvalue()))
        page.get_by_role('button', name='Transcribe clip').click()
        identifier = None
        try:
            page.get_by_role('button', name='Delete job and its audio').wait_for(timeout=30000)
            jobs = page.request.get(base+'/api/jobs').json()
            job = next(job for job in jobs if job['filename'] == 'onboarding-silence.wav')
            identifier = job['id']
            assert job['state'] == 'completed' and job['pipelines'] == ['direct']
            assert job['model_profile'] == 'aligned'
            assert job['inference']['word_timestamps'] is True
            for width in (1440, 390):
                page.set_viewport_size(dict(width=width, height=1000))
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert not errors, errors
            page.get_by_role('button', name='New transcription', exact=True).click()
            page.get_by_role('heading', name='Drop a little music here').wait_for()
            page.screenshot(path=str(output/'upload-mobile.png'), full_page=True)
            assert not page.get_by_label('Recognition model').is_visible()
            assert page.get_by_label('Audio language').is_visible()
            page.get_by_text('Transcribe multiple recordings', exact=True).click()
            batch = page.locator('.batch-upload')
            batch.get_by_label('Batch audio files', exact=True).set_input_files([
                dict(name='batch-owned-one.wav', mimeType='audio/wav', buffer=data.getvalue()),
                dict(name='batch-owned-two.wav', mimeType='audio/wav', buffer=data.getvalue()),
            ])
            uploads = []
            def full_queue_once(route):
                if route.request.method == 'POST':
                    uploads.append(1)
                    if len(uploads) == 2:
                        route.fulfill(status=429, json={'detail': 'Local queue is full'})
                        return
                route.continue_()
            page.route('**/api/jobs', full_queue_once)
            batch.get_by_role('button', name='Send pending recordings', exact=True).click()
            batch.get_by_text('batch-owned-two.wav: failed', exact=False).wait_for()
            assert batch.get_by_text('batch-owned-one.wav: accepted', exact=True).count() == 1
            batch.get_by_role('button', name='Send pending recordings', exact=True).click()
            batch.get_by_text('batch-owned-two.wav: accepted', exact=True).wait_for()
            assert len(uploads) == 3
            assert batch.get_by_role('button', name='Send pending recordings', exact=True).is_disabled()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.unroute('**/api/jobs', full_queue_once)
            print('Passed: simple upload, collapsed advanced settings, aligned selection, local silence processing and mobile layout. Model readiness mocked; no checkpoint quality claim.')
        finally:
            if identifier:
                page.request.delete(base+'/api/jobs/'+identifier)
            for item in page.request.get(base+'/api/jobs').json():
                if item['filename'] in {'batch-owned-one.wav', 'batch-owned-two.wav'}:
                    import time
                    for _ in range(100):
                        state = page.request.get(base+'/api/jobs/'+item['id']).json()['state']
                        if state not in {'queued', 'processing'}:
                            break
                        time.sleep(.1)
                    assert page.request.delete(base+'/api/jobs/'+item['id']).status == 204
            browser.close()


if __name__ == '__main__':
    main()
