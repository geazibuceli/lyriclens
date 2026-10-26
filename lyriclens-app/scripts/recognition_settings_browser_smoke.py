"""Verify recognition controls with isolated API fixtures; no model inference."""
import io
import json
import os
import wave
from email.parser import BytesParser
from email.policy import default
from playwright.sync_api import sync_playwright, expect


def main():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(bytes(128000))
    source = buffer.getvalue()
    submitted, retries, jobs, errors = [], [], [], []
    fixture = dict(id='recognition-fixture', filename='own-silence.wav', state='completed',
                   stage='Finished', requested_language='en', model_profile='large-v3',
                   inference={'hallucination_silence_threshold': 2.0},
                   audio={'duration': 4}, pipelines=['direct', 'vocals'],
                   created_at='2026-10-26T12:00:00Z', results={'direct': dict(
                       state='completed', seconds=0, edited=None, detected_language='en',
                       original=[dict(start=.2, end=2.8, text='Owned fixture words')])})
    models = dict(prepared=True, ffmpeg_available=True, separation_prepared=True,
                  languages={'en': 'English', 'ja': 'Japanese'}, profiles=[
                      dict(id=value, label=value, prepared=True, note='Fixture')
                      for value in ('configured', 'aligned', 'large-v3')])
    base = os.environ.get('LYRICLENS_BROWSER_URL', 'http://127.0.0.1:5181')

    def api(route):
        request = route.request
        path = request.url.split('/api', 1)[1]
        if path == '/jobs' and request.method == 'POST':
            header = ('Content-Type: ' + request.headers['content-type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode()
            message = BytesParser(policy=default).parsebytes(header + request.post_data_buffer)
            fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True).decode()
                      for part in message.iter_parts() if not part.get_filename()}
            submitted.append(fields)
            jobs.append(fixture)
            route.fulfill(status=202, json=fixture)
        elif path.endswith('/retranscribe'):
            retries.append(request.post_data_json)
            route.fulfill(status=409, json={'detail': 'Fixture request captured; no inference started.'})
        elif path == '/jobs':
            route.fulfill(json=jobs)
        elif path == '/models':
            route.fulfill(json=models)
        elif path == '/diagnostics':
            route.fulfill(json={'checks': [], 'note': 'Fixture'})
        elif path.endswith('/audio'):
            route.fulfill(body=source, content_type='audio/wav')
        else:
            route.fulfill(json={})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/**', api)
        page.goto(base)
        guard = page.get_by_role('checkbox', name='Reduce suspected hallucinations around instrumental gaps (experimental)', exact=True)
        expect(guard).not_to_be_checked()
        page.get_by_role('button', name='Try Large-v3 + compare vocals', exact=True).click()
        expect(guard).not_to_be_checked()
        guard.check()
        expect(guard).to_be_checked()
        page.get_by_label('Audio language', exact=True).select_option('en')
        page.get_by_text('Advanced transcription options', exact=True).click()
        expect(page.get_by_label('Recognition model', exact=True)).to_have_value('large-v3')
        expect(page.get_by_label('Listening mode', exact=True)).to_have_value('both')
        page.get_by_label('Upload music clip', exact=True).set_input_files(
            {'name': 'own-silence.wav', 'mimeType': 'audio/wav', 'buffer': source})
        page.get_by_role('button', name='Transcribe clip', exact=True).click()
        page.locator('.region-retry summary').click()
        assert submitted == [{'language': 'en', 'pipeline': 'both', 'model_profile': 'large-v3', 'reduce_hallucinations': 'true'}], submitted
        expect(page.get_by_label('Passage language instruction', exact=True)).to_have_value('en')
        page.get_by_label('Passage recognition model', exact=True).select_option('aligned')
        page.locator('.region-retry').get_by_role('checkbox').uncheck()
        page.get_by_role('button', name='Retranscribe passage', exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('Fixture request captured')
        assert retries == [dict(language='en', reduce_hallucinations=False, model_profile='aligned',
                                pipeline='direct', start=.2, end=2.8, context_seconds=2)], retries
        page.get_by_role('button', name='Run again with a different language or mode', exact=False).click()
        expect(page.get_by_label('Audio language', exact=True)).to_have_value('en')
        expect(guard).to_be_checked()
        page.get_by_text('Advanced transcription options', exact=True).click()
        expect(page.get_by_label('Listening mode', exact=True)).to_have_value('both')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button', name='Filter instrumental sections', exact=True).click()
        expect(page.get_by_label('Listening mode', exact=True)).to_have_value('vocals')
        expect(page.get_by_label('Recognition model', exact=True)).to_have_value('large-v3')
        expect(guard).to_be_checked()
        assert not errors, errors
        browser.close()
    print('Recognition UI passed: quality preset, language, guard payload, region override, rerun settings and mobile.')


if __name__ == '__main__':
    main()
