"""Verify deletion during browser audio playback using an owned digital-silence fixture."""
import tempfile
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
        fixture = Path(tmp)/'delete-browser-check.wav'
        with wave.open(str(fixture), 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(bytes(32000*120))
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('http://127.0.0.1:5181')
        page.get_by_label('Upload music clip').set_input_files(fixture)
        page.get_by_label('Listening mode').select_option('direct')
        with page.expect_response(lambda response: response.request.method=='POST' and response.url.endswith('/api/jobs')) as created:
            page.get_by_role('button', name='Transcribe clip').click()
        job_id = created.value.json()['id']
        button = page.get_by_role('button', name='Delete job and its audio')
        button.wait_for(timeout=30000)
        assert page.request.get(f'http://127.0.0.1:5181/api/jobs/{job_id}').json()['filename']==fixture.name
        player = page.get_by_label('Original clip playback')
        player.evaluate('(audio) => audio.play()')
        page.wait_for_function("Array.from(document.querySelectorAll('audio')).some(a => !a.paused && a.currentTime > 0)")
        with page.expect_response(lambda response: response.request.method=='DELETE' and response.url.endswith('/jobs/'+job_id)) as event:
            button.click()
        assert event.value.status==204, event.value.text()
        page.get_by_role('button', name='Transcribe clip').wait_for()
        assert page.request.get(f'http://127.0.0.1:5181/api/jobs/{job_id}').status==404
        assert not any(j['id']==job_id for j in page.request.get('http://127.0.0.1:5181/api/jobs').json())
        print('Passed: own 120-second audio playing in Chromium deleted with HTTP 204; record removed.')
        browser.close()


if __name__=='__main__':
    main()
