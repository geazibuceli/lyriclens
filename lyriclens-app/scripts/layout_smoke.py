"""Read-only regression check: CSS must load and keep the workspace responsive."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    output = Path(__file__).resolve().parents[1]/'artifacts/layout'
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        for width,height in [(1440,1000),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            page.goto('http://127.0.0.1:5181')
            page.get_by_role('heading',name='Drop a little music here').wait_for()
            page.wait_for_function("Array.from(document.styleSheets).some(s => s.cssRules.length > 50)")
            styles = page.evaluate("Array.from(document.styleSheets).reduce((sum,s)=>sum+s.cssRules.length,0)")
            assert styles>50, f'Stylesheet missing or empty: {styles} rules'
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Overflow at {width}px'
            page.screenshot(path=str(output/f'workspace-{width}.png'),full_page=True)
        assert not errors,errors
        browser.close()
        print('Passed: stylesheet loaded, desktop/mobile layout has no horizontal overflow or browser errors.')


if __name__=='__main__':
    main()
