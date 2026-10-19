"""Owned-silence editor/draft/archive workflow; no recognition models required."""
import os
import io
import json
import time
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parents[1]
    output=root/'artifacts/browser-editor'
    output.mkdir(parents=True,exist_ok=True)
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'));audio.writeframes(bytes(128000))
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        base=os.environ.get('LYRICLENS_BROWSER_URL','http://127.0.0.1:5181');ids=[]
        response=page.request.post(base+'/api/jobs',multipart={'file':{'name':'editor-ui-fixture.wav','mimeType':'audio/wav','buffer':buffer.getvalue()},'language':'en'})
        assert response.status==202,response.text()
        identifier=response.json()['id'];ids.append(identifier)
        path=base+'/api/jobs/'+identifier
        try:
            for _ in range(300):
                job=page.request.get(path).json()
                if job['state'] not in ('queued','processing'):break
                time.sleep(.1)
            assert job['state']=='completed'
            original=[dict(start=.1,end=1.8,text='Hello 世界',language='en'),dict(start=2,end=3.8,text='Second own line',language='en')]
            assert page.request.put(path+'/edit',data=dict(pipeline='direct',segments=original)).status==200
            page.goto(base+'/?job='+identifier)
            editor=page.locator('.transcript').first
            first=editor.get_by_label('Segment 1 transcript',exact=True)
            first.wait_for();first.fill('Unsaved café世界')
            draft_key='lyriclens:draft:v1:'+identifier+':direct'
            page.wait_for_function('(key)=>localStorage.getItem(key)?.includes("Unsaved")',arg=draft_key)
            page.reload();first.wait_for()
            assert first.input_value()==original[0]['text']
            editor.get_by_role('button',name='Restore browser draft',exact=True).click()
            assert first.input_value()=='Unsaved café世界'
            assert page.request.get(path+'/export').text().startswith('Hello 世界')
            editor.get_by_label('Search transcript',exact=True).fill('CAFÉ')
            editor.get_by_role('button',name='Segment 1 at 00:00:',exact=False).click()
            assert abs(page.get_by_label('Original clip playback',exact=True).evaluate('audio=>audio.currentTime')-.1)<.5
            editor.get_by_text('Split or merge segment 1',exact=True).click()
            editor.get_by_label('Segment 1 split seconds',exact=True).fill('0.9')
            editor.get_by_label('Segment 1 text cut',exact=True).fill('7')
            editor.get_by_role('button',name='Split segment 1',exact=True).click()
            assert editor.locator('textarea').count()==3
            assert first.input_value()=='Unsaved'
            assert editor.get_by_label('Segment 2 transcript',exact=True).input_value()==' café世界'
            assert editor.get_by_label('Segment 2 start seconds',exact=True).input_value()=='0.9'
            editor.get_by_role('button',name='Merge segment 1 with next',exact=True).click()
            assert editor.locator('textarea').count()==2
            assert first.input_value()=='Unsaved\n café世界'
            undo=editor.get_by_role('button',name='Undo transcript edit',exact=True)
            undo.click();assert editor.locator('textarea').count()==3
            undo.click();assert editor.locator('textarea').count()==2
            editor.get_by_label('Segment 2 language',exact=True).select_option('pt')
            editor.get_by_role('button',name='Merge segment 1 with next',exact=True).click()
            assert editor.locator('textarea').count()==2
            assert 'same language' in editor.inner_text()
            undo.click()
            first.press('Control+Enter')
            editor.get_by_role('button',name='Saved',exact=True).wait_for()
            page.wait_for_function('(key)=>localStorage.getItem(key)===null',arg=draft_key)
            first.fill('Conflict draft')
            page.wait_for_function('(key)=>localStorage.getItem(key)?.includes("Conflict")',arg=draft_key)
            changed=[{**original[0],'text':'Updated saved source'},original[1]]
            assert page.request.put(path+'/edit',data=dict(pipeline='direct',segments=changed)).status==200
            page.reload();first.wait_for()
            assert first.input_value()=='Updated saved source'
            assert 'saved source changed' in editor.inner_text()
            editor.get_by_role('button',name='Discard browser draft',exact=True).click()
            assert first.input_value()=='Updated saved source'
            page.get_by_text('Backup and restore a job',exact=True).click()
            with page.expect_download() as downloaded:
                page.get_by_role('link',name='Download this job backup',exact=True).click()
            archive=output/'owned-job.lyriclens.zip'
            downloaded.value.save_as(str(archive))
            page.get_by_label('Job backup ZIP',exact=True).set_input_files(str(archive))
            page.get_by_role('button',name='Restore as a separate job',exact=True).click()
            page.wait_for_function('(old)=>document.querySelector("audio")?.getAttribute("src") && !document.querySelector("audio").getAttribute("src").includes(old)',arg=identifier)
            restored=page.get_by_label('Original clip playback',exact=True).get_attribute('src').split('/')[3]
            ids.append(restored)
            assert page.request.get(base+'/api/jobs/'+restored+'/audio').body()==buffer.getvalue()
            assert page.request.get(base+'/api/jobs/'+restored+'/export').text().startswith('Updated saved source')
            assert page.request.get(path).status==200
            for width,height in [(1440,1000),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/f'editor-{width}.png'),full_page=True)
            page.add_script_tag(path=str(root/'frontend/node_modules/axe-core/axe.min.js'))
            audit=page.evaluate("async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
            (output/'accessibility.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
            assert not audit['violations'],[(v['id'],v['help']) for v in audit['violations']]
            assert not errors,errors
            print('Passed: persistent Unicode draft, explicit restore/conflict discard, search/seek, split/merge/undo/language guard, ZIP download/restore without replacement, mobile and axe. Owned silence; no model download.')
        finally:
            page.close();context=browser.new_context()
            for item in reversed(ids):
                assert context.request.delete(base+'/api/jobs/'+item).status==204
            browser.close()


if __name__=='__main__':main()
