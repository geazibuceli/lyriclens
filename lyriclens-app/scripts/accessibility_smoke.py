"""Run local axe checks against upload/results at desktop and mobile widths."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:5181')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    reports=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for width,height in [(1440,1100),(390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height})
            for state in ['upload','results']:
                page.goto(args.url)
                page.get_by_role('heading',name='Drop a little music here').wait_for()
                if state=='results':
                    page.locator('.job-link').first.click()
                    page.locator('.transcript').first.wait_for()
                page.add_script_tag(path=str(root/'frontend'/'node_modules'/'axe-core'/'axe.min.js'))
                result=page.evaluate("async () => await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
                reports.append({'width':width,'state':state,'violations':result['violations'],'incomplete':result['incomplete']})
            page.close()
        browser.close()
    output=root/'artifacts'/'browser'/'accessibility.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(reports,indent=2),encoding='utf-8')
    print(json.dumps([{'width':r['width'],'state':r['state'],'violations':[{'id':v['id'],'impact':v['impact'],'nodes':len(v['nodes'])} for v in r['violations']]} for r in reports],indent=2))
    if any(r['violations'] for r in reports):
        raise SystemExit(1)


if __name__=='__main__':
    main()
