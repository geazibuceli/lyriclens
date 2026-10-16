"""Browser MP4 upload/playback/deletion check with a generated silent video."""
import hashlib
import subprocess
import tempfile
from pathlib import Path
import imageio_ffmpeg
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
        source = Path(tmp)/'mp4-browser-check.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-y',
                        '-f','lavfi','-i','color=c=blue:s=64x64:r=10:d=3.2',
                        '-f','lavfi','-i','anullsrc=r=44100:cl=stereo',
                        '-t','3.2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],
                       check=True,capture_output=True,timeout=30)
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('http://127.0.0.1:5181')
        page.get_by_label('Upload music clip').set_input_files(source)
        page.get_by_label('Listening mode').select_option('direct')
        with page.expect_response(lambda response: response.request.method=='POST' and response.url.endswith('/api/jobs')) as created:
            page.get_by_role('button',name='Transcribe clip').click()
        assert created.value.status==202
        identifier = created.value.json()['id']
        button = page.get_by_role('button',name='Delete job and its audio')
        button.wait_for(timeout=30000)
        job = page.request.get('http://127.0.0.1:5181/api/jobs/'+identifier).json()
        assert job['state']=='completed',job
        assert job['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
        assert job['audio']['sample_rate']==16000
        assert job['audio']['channels']==1
        assert abs(job['audio']['duration']-3.2)<.1
        player = page.get_by_label('Original clip playback')
        player.evaluate('(audio) => audio.play()')
        page.wait_for_function("Array.from(document.querySelectorAll('audio')).some(a => !a.paused && a.currentTime > 0)")
        with page.expect_response(lambda response: response.request.method=='DELETE' and response.url.endswith('/jobs/'+identifier)) as removed:
            button.click()
        assert removed.value.status==204
        assert page.request.get('http://127.0.0.1:5181/api/jobs/'+identifier).status==404
        browser.close()
        print('Passed: MP4 H.264/AAC upload, first-audio-track extraction, original preservation, playback and deletion.')


if __name__=='__main__':
    main()
