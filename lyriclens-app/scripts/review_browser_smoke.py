"""Browser regression for speed and bounded segment repeat, using an owned silence fixture."""
import os
import json
import tempfile
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'artifacts/browser-review'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
        fixture = Path(tmp)/'review-browser-check.wav'
        with wave.open(str(fixture),'wb') as audio:
            audio.setparams((1,2,16000,0,'NONE','not compressed'))
            audio.writeframes(bytes(32000*4))
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        base = os.environ.get('LYRICLENS_BROWSER_URL','http://127.0.0.1:5181')
        response = page.request.post(base+'/api/jobs',multipart={
            'file':{'name':fixture.name,'mimeType':'audio/wav','buffer':fixture.read_bytes()},'language':'en'})
        assert response.status==202
        identifier = response.json()['id']
        path = base+'/api/jobs/'+identifier
        try:
            page.goto(base+'/?job='+identifier)
            page.get_by_role('button',name='Delete job and its audio').wait_for(timeout=30000)
            segments = [dict(start=.4,end=.9,text='First review line.'),dict(start=1.5,end=2.2,text='Second review line.')]
            assert page.request.put(path+'/edit',data={'pipeline':'direct','segments':segments}).status==200
            exported = page.request.get(path+'/export?format=srt').text()
            page.reload()
            speed = page.get_by_label('Playback speed',exact=True)
            speed.wait_for()
            speed.select_option('0.5')
            player = page.get_by_label('Original clip playback')
            assert player.evaluate('(a) => a.playbackRate')==.5
            assert player.evaluate('(a) => a.preservesPitch')
            player.evaluate("a => { window.reviewSeeks=[]; a.addEventListener('seeked',()=>window.reviewSeeks.push(a.currentTime)); }")
            first = page.get_by_role('button',name='Repeat segment 1',exact=True)
            first.click()
            assert first.get_attribute('aria-pressed')=='true'
            page.wait_for_function('window.reviewSeeks.filter(t => Math.abs(t-.4)<.15).length >= 3',timeout=15000)
            assert player.evaluate('(a) => a.currentTime >= .39 && a.currentTime < 1.05')
            page.get_by_role('button',name='Repeat segment 2',exact=True).click()
            page.wait_for_function("document.querySelector('audio').currentTime >= 1.49 && document.querySelector('audio').currentTime < 2.3")
            assert first.get_attribute('aria-pressed')=='false'
            page.get_by_role('button',name='Stop repeat',exact=True).click()
            assert player.evaluate('(a) => a.paused')
            first.click()
            first.click()
            assert first.get_attribute('aria-pressed')=='false' and player.evaluate('(a) => a.paused')
            first.click()
            page.get_by_label('Segment 1 start seconds',exact=True).fill('0.6')
            assert player.evaluate('(a) => a.paused')
            assert first.get_attribute('aria-pressed')=='false'
            assert page.request.get(path+'/export?format=srt').text()==exported
            for width,height in [(1440,1000),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(output/f'review-{width}.png'),full_page=True)
            page.add_script_tag(path=str(root/'frontend/node_modules/axe-core/axe.min.js'))
            audit = page.evaluate("async () => await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
            (output/'accessibility.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
            assert not audit['violations'],[(v['id'],v['help']) for v in audit['violations']]
            first.click()
            page.get_by_role('button',name='New transcription',exact=True).click()
            assert page.get_by_label('Original clip playback').count()==0
            assert not errors,errors
            print('Passed: 0.5x pitch-preserving playback, repeated segment wraps, switching/stopping repeat, timing-edit reset, unchanged SRT, responsive layout and axe audit.')
        finally:
            page.close()
            removed = browser.new_context().request.delete(path)
            assert removed.status==204,removed.text()
            browser.close()


if __name__=='__main__':
    main()
