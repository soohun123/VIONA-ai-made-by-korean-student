"""Resume an existing completed real generation; verify its saved image in both layouts."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
job=json.loads((ROOT/'local-media-generate-validation.json').read_text(encoding='utf-8'))['job']
record={'id':job['id'],'kind':'generate','prompt':'빨간 로봇 그림'}
result={'checks':{},'errors':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    for name,width,height in [('desktop',1366,900),('mobile',390,844)]:
        context=browser.new_context(viewport={'width':width,'height':height},is_mobile=name=='mobile')
        context.add_init_script('localStorage.setItem("novabrain-media-job",'+json.dumps(json.dumps(record,ensure_ascii=False))+');')
        page=context.new_page();page.on('pageerror',lambda e:result['errors'].append(str(e)))
        page.goto('http://127.0.0.1:8000'+('/mobile' if name=='mobile' else ''),wait_until='networkidle')
        expect(page.locator('#log .message-image')).to_have_count(1)
        expect(page.locator('#send')).to_be_enabled()
        image=page.locator('#log .message-image')
        assert image.evaluate('(img)=>img.complete && img.naturalWidth===384')
        page.locator('#mediaShortcut').click()
        expect(page.locator('#mediaResult img')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(ROOT/('media-'+name+'-verified.png')))
        result['checks'][name+'_resume_real_generated_image']=True
        context.close()
    browser.close()
assert not result['errors'],result['errors']
(ROOT/'media-resume-ui-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
