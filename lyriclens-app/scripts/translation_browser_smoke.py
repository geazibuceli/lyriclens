"""Real local translation UI/export/staleness diagnostic on an owned silence fixture."""
import json
import tempfile
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'artifacts/browser-translation'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
        source = Path(tmp)/'translation-browser-check.wav'
        with wave.open(str(source),'wb') as audio:
            audio.setparams((1,2,16000,0,'NONE','not compressed'))
            audio.writeframes(bytes(32000*3))
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1100})
        errors = []
        page.on('pageerror',lambda error: errors.append(str(error)))
        base = 'http://127.0.0.1:5181'
        created = page.request.post(base+'/api/jobs',multipart={
            'file':{'name':source.name,'mimeType':'audio/wav','buffer':source.read_bytes()},
            'language':'en','pipeline':'direct'})
        assert created.status==202,created.text()
        identifier = created.json()['id']
        path = base+'/api/jobs/'+identifier
        try:
            page.goto(base+'/?job='+identifier)
            page.get_by_role('button',name='Delete job and its audio').wait_for(timeout=30000)
            page.wait_for_function("getComputedStyle(document.querySelector('.app')).display === 'flex'")
            assert page.evaluate("Array.from(document.styleSheets).some(s => s.cssRules.length > 50)")
            edited = page.request.put(path+'/edit',data={'pipeline':'direct','segments':[{'start':.2,'end':2.5,'text':'The sun is shining today.'}]})
            assert edited.status==200
            page.reload()
            panel = page.locator('.translation-panel')
            page.get_by_role('button',name='Translate transcript',exact=True).click()
            assert panel.evaluate('(element) => element.open')
            panel.get_by_label('Translation source language').select_option('en')
            panel.get_by_label('Translation target language').select_option('pt')
            panel.get_by_role('button',name='Translate saved text',exact=True).click()
            field = panel.get_by_label('Translated segment 1',exact=True)
            field.wait_for(timeout=60000)
            assert field.input_value().strip()
            saved = page.request.get(path).json()
            item = saved['translations']['direct:pt']
            assert item['state']=='completed' and item['source_version']=='edited'
            assert item['source_segments'][0]['text']=='The sun is shining today.'
            assert item['segments'][0]['start']==.2 and item['segments'][0]['end']==2.5
            assert saved['results']['direct']['original']==[]
            page.screenshot(path=str(output/'desktop.png'),full_page=True)
            text = 'Revisão: olá 안녕 日本語 中文'
            field.fill(text)
            draft_key='lyriclens:draft:v1:'+identifier+':direct:translation:pt'
            page.wait_for_function('(args)=>localStorage.getItem(args.key)?.includes(args.text)',arg={'key':draft_key,'text':text})
            page.reload()
            page.get_by_role('button',name='Translate transcript',exact=True).click()
            field.wait_for()
            assert field.input_value()!=text
            panel.get_by_role('button',name='Restore browser draft',exact=True).click()
            assert field.input_value()==text
            assert page.request.get(path).json()['translations']['direct:pt']['edited'] is None
            with page.expect_response(lambda r: r.request.method=='PUT' and r.url.endswith('/translation')) as updated:
                panel.get_by_role('button',name='Save translation edits',exact=True).click()
            assert updated.value.status==200
            panel.get_by_text('Export translation',exact=True).click()
            with page.expect_download() as downloaded:
                panel.get_by_role('link',name='SRT',exact=True).click()
            downloaded.value.save_as(output/'edited.srt')
            exported = (output/'edited.srt').read_text(encoding='utf-8')
            assert text in exported and '00:00:00,200 --> 00:00:02,500' in exported
            with page.expect_download() as bilingual:
                panel.get_by_role('link',name='Bilingual SRT',exact=True).click()
            bilingual.value.save_as(output/'bilingual.srt')
            combined=(output/'bilingual.srt').read_text(encoding='utf-8')
            assert 'The sun is shining today.\n'+text in combined
            assert '00:00:00,200 --> 00:00:02,500' in combined
            original = page.get_by_role('textbox',name='Segment 1 transcript',exact=True)
            original.fill('The sky is blue.')
            page.get_by_role('button',name='Save edits',exact=True).click()
            panel.get_by_text('The source transcript changed. Translate again before editing or exporting this translation.',exact=True).wait_for()
            assert page.request.get(path+'/export?translation=pt').status==409
            panel.get_by_role('button',name='Translate saved text again',exact=True).click()
            page.wait_for_function("async url => { const r = await fetch(url); const j = await r.json(); return j.translations['direct:pt'].state === 'completed' && !j.translations['direct:pt'].stale; }",arg='/api/jobs/'+identifier)
            assert page.request.get(path).json()['translations']['direct:pt']['source_segments'][0]['text']=='The sky is blue.'
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.add_script_tag(path=str(root/'frontend/node_modules/axe-core/axe.min.js'))
            audit = page.evaluate("async () => await axe.run(document, {runOnly: {type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
            (output/'accessibility.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
            assert not audit['violations'],[(v['id'],v['help']) for v in audit['violations']]
            assert not errors,errors
            print('Passed: real translation, persistent translation draft/explicit restore, source preservation, Unicode edits, bilingual SRT timing, stale-source guard, retranslation, mobile layout and axe audit.')
        finally:
            page.close()
            removed = browser.new_context().request.delete(path)
            assert removed.status==204,removed.text()
            browser.close()


if __name__=='__main__':
    main()
