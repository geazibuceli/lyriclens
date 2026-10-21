"""Opt-in browser integration test against running real backend and frontend."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from lyriclens.profiles import PROFILE_IDS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:5181')
    parser.add_argument('--model-profile',choices=PROFILE_IDS,default='configured')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=root/'artifacts'/('browser' if args.model_profile=='configured' else f'browser-{args.model_profile}')
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1100})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role('heading',name='Drop a little music here').wait_for()
        page.screenshot(path=str(output/'desktop-upload.png'),full_page=True)
        page.get_by_label('Upload music clip').set_input_files(root/'evaluation'/'audio'/'singing'/'mary.wav')
        page.get_by_label('Audio language').select_option('en')
        page.get_by_text('Advanced transcription options', exact=True).click()
        page.get_by_label('Recognition model').select_option(args.model_profile)
        page.get_by_label('Listening mode').select_option('both')
        page.get_by_role('button',name='Transcribe clip').click()
        page.get_by_role('button',name='Delete job and its audio').wait_for(timeout=240000)
        assert page.locator('.transcript').count()==2
        assert page.get_by_role('heading',name='Original audio',exact=True).count()==1
        assert page.get_by_role('heading',name='Isolated vocals',exact=True).count()==1
        assert page.locator('.transcript .error').count()==0, page.locator('.transcript').all_text_contents()
        page.screenshot(path=str(output/'desktop-results.png'),full_page=True)
        first=page.locator('.transcript').first
        first.get_by_role('textbox',name='Segment 1 transcript',exact=True).fill('UI verification edit — 안녕 日本語 中文 olá')
        first.get_by_role('button',name='Save edits',exact=True).click()
        first.get_by_role('button',name='Saved',exact=True).wait_for()
        first.locator('.timestamp').first.click()
        page.wait_for_function("document.querySelector('audio').currentTime > 0")
        first.get_by_text('Export',exact=True).click()
        with page.expect_download() as event:
            first.get_by_role('link',name='SRT',exact=True).click()
        event.value.save_as(output/'edited.srt')
        assert '안녕' in (output/'edited.srt').read_text(encoding='utf-8')
        jobs=page.request.get(args.url+'/api/jobs').json()
        job=next(j for j in jobs if j['filename']=='mary.wav' and j.get('model_profile','configured')==args.model_profile and j['results'].get('direct',{}).get('edited'))
        assert job.get('model_profile','configured')==args.model_profile
        if args.model_profile=='large-v3':
            assert job['model_id']=='Systran/faster-whisper-large-v3'
        if args.model_profile=='aligned':
            assert job['inference']['word_timestamps'] is True
        assert 'UI verification' not in job['results']['direct']['original_text']
        assert job['results']['direct']['edited'][0]['text'].startswith('UI verification')
        (output/'real-job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(output/'mobile-results.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.set_viewport_size({'width':1440,'height':1100})
        first.get_by_label('Segment 1 start seconds',exact=True).fill('5')
        first.get_by_label('Segment 1 end seconds',exact=True).fill('9')
        first.get_by_role('button',name='Save edits',exact=True).click()
        first.get_by_role('button',name='Saved',exact=True).wait_for()
        first.get_by_text('Experimental: retranscribe a passage in another language',exact=True).click()
        first.get_by_label('Passage language instruction',exact=True).select_option('en')
        first.get_by_role('button',name='Retranscribe passage',exact=True).click()
        page.wait_for_url('**/?job=*')
        page.get_by_role('button',name='Delete job and its audio').wait_for(timeout=180000)
        child_id=page.url.split('job=')[-1]
        child=page.request.get(args.url+'/api/jobs/'+child_id).json()
        assert child['state']=='completed',child
        assert child['region']['start']==3
        assert child['region']['end']==11
        assert child['processed_audio']['original_offset']==3
        assert all(s['start']>=3 and s['end']<=11 for s in child['results']['direct']['original'])
        assert child['source_job_id']==job['id']
        assert child['model_id']==job['model_id'] and child['revision']==job['revision']
        assert child['inference']==job['inference']
        (output/'region-job.json').write_text(json.dumps(child,ensure_ascii=False,indent=2),encoding='utf-8')
        page.screenshot(path=str(output/'region-results.png'),full_page=True)
        assert not errors, errors
        print(json.dumps({'status':'passed','job_id':job['id'],'pipelines':list(job['results']),'browser_errors':errors,'screenshots':str(output)},indent=2))
        browser.close()


if __name__=='__main__':
    main()
