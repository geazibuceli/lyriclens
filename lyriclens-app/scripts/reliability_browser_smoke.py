"""Owned-fixture UI check for editor history, waveform and generated-cache cleanup."""
import os
import io
import json
import wave
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'artifacts/browser-reliability'
    output.mkdir(parents=True,exist_ok=True)
    buffer = io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'))
        audio.writeframes(bytes(128000))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror',lambda error: errors.append(str(error)))
        base = os.environ.get('LYRICLENS_BROWSER_URL','http://127.0.0.1:5181')
        response = page.request.post(base+'/api/jobs',multipart={
            'file':{'name':'reliability-ui-fixture.wav','mimeType':'audio/wav','buffer':buffer.getvalue()},'language':'en'})
        assert response.status == 202, response.text()
        identifier = response.json()['id']
        path = base+'/api/jobs/'+identifier
        try:
            for _ in range(300):
                job = page.request.get(path).json()
                if job['state'] not in ('queued','processing'): break
                time.sleep(.1)
            assert job['state'] == 'completed'
            segments = [dict(start=.1,end=1.8,text='Repeat this sample line',language='en'),
                        dict(start=2,end=3.9,text='Repeat this sample line',language='en')]
            assert page.request.put(path+'/edit',data=dict(pipeline='direct',segments=segments)).status == 200
            page.goto(base+'/?job='+identifier)
            editor = page.locator('.transcript').first
            first = editor.get_by_label('Segment 1 transcript',exact=True)
            first.wait_for()
            assert 'Same text as previous passage' in editor.inner_text()
            undo = editor.get_by_role('button',name='Undo transcript edit',exact=True)
            redo = editor.get_by_role('button',name='Redo transcript edit',exact=True)
            assert undo.is_disabled()
            first.fill('Corrected sample line')
            first.press('Control+z')
            assert first.input_value() == segments[0]['text']
            first.press('Control+Shift+z')
            assert first.input_value() == 'Corrected sample line'
            editor.get_by_label('Segment 1 language',exact=True).select_option('pt')
            undo.click()
            assert editor.get_by_label('Segment 1 language',exact=True).input_value() == 'en'
            editor.get_by_label('Segment 1 start seconds',exact=True).fill('0.5')
            undo.click()
            assert editor.get_by_label('Segment 1 start seconds',exact=True).input_value() == '0.1'
            editor.get_by_role('button',name='Remove segment 2',exact=True).click()
            assert editor.locator('.segments textarea').count() == 1
            undo.click()
            assert editor.locator('.segments textarea').count() == 2
            editor.get_by_role('button',name='+ Add segment',exact=True).click()
            assert editor.locator('.segments textarea').count() == 3
            undo.click()
            assert editor.locator('.segments textarea').count() == 2
            first.press('Control+Enter')
            editor.get_by_role('button',name='Saved',exact=True).wait_for()
            assert page.request.get(path+'/export').text().startswith('Corrected sample line')
            undo.click()
            assert first.input_value() == segments[0]['text']
            assert editor.get_by_role('button',name='Save edits',exact=True).is_enabled()
            redo.click()
            assert editor.get_by_role('button',name='Saved',exact=True).is_disabled()
            first.fill('SamplePhrase'*3)
            editor.get_by_text('Review suggestion: Repeated text pattern',exact=False).wait_for()
            undo.click()
            editor.get_by_label('Segment 1 end seconds',exact=True).fill('22')
            editor.get_by_text('Review suggestion: Long passage',exact=False).wait_for()
            undo.click()
            page.get_by_role('button',name='Load audio waveform',exact=True).click()
            slider = page.get_by_label('Waveform position seconds',exact=True)
            slider.wait_for()
            slider.press('End')
            slider.press('ArrowLeft')
            player = page.get_by_label('Original clip playback',exact=True)
            assert player.evaluate('audio => audio.currentTime') > 3.9
            assert page.request.get(path+'/audio').body() == buffer.getvalue()
            page.get_by_text('Environment checks',exact=False).first.click()
            page.get_by_role('button',name='Refresh environment checks',exact=True).wait_for()
            page.get_by_text('Local storage and cache',exact=True).click()
            page.get_by_role('button',name='Measure local storage',exact=True).click()
            clear = page.get_by_role('button',name='Clear generated cache for reliability-ui-fixture.wav',exact=True)
            clear.wait_for()
            assert clear.is_enabled()
            clear.click()
            page.wait_for_function("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Clear generated cache for reliability-ui-fixture.wav' && b.disabled)")
            assert page.request.get(path+'/export').text().startswith('Corrected sample line')
            assert page.request.get(path+'/audio').body() == buffer.getvalue()
            for width,height in [(1440,1000),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output/f'reliability-{width}.png'),full_page=True)
            page.add_script_tag(path=str(root/'frontend/node_modules/axe-core/axe.min.js'))
            audit = page.evaluate("async () => await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
            (output/'accessibility.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
            assert not audit['violations'],[(v['id'],v['help']) for v in audit['violations']]
            assert not errors,errors
            print('Passed: undo/redo for text/language/timing/removal/addition, save shortcut and saved baseline, repeat suggestion, waveform seek, diagnostics, scoped cache cleanup, preserved original/text, desktop/mobile and axe.')
        finally:
            page.close()
            context = browser.new_context()
            assert context.request.delete(path).status == 204
            browser.close()


if __name__=='__main__':
    main()
