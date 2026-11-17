import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from api_credentials import load_api_key
ROOT=Path(__file__).resolve().parent
url=json.loads((ROOT/'network-settings.json').read_text())['public_url']
report={'url':url}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1280,'height':900})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url,wait_until='networkidle')
    expect(page.locator('h1')).to_have_text('VIONA')
    page.locator('input[name=key]').fill(load_api_key())
    page.locator('form button').click()
    expect(page.locator('#modelButton')).to_contain_text('VIONA',timeout=30000)
    expect(page.locator('#openDesktop')).to_be_hidden()
    report['remote_desktop_hidden']=True
    page.locator('#searchToggle').click();page.locator('#searchToggle').click()
    page.locator('#prompt').fill('너의 이름만 알려줘.')
    page.locator('#send').click()
    expect(page.locator('.message.assistant')).to_have_count(1)
    expect(page.locator('#send')).to_be_enabled(timeout=240000)
    reply=page.locator('.message.assistant').last.inner_text()
    assert 'VIONA' in reply,reply
    report.update({'title':page.title(),'reply':reply,'javascript_errors':errors})
    assert not errors
    page.reload(wait_until='networkidle')
    expect(page.locator('#log')).to_contain_text('VIONA')
    report['https_history_persisted']=True
    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    m=mobile.new_page();m.goto(url,wait_until='networkidle')
    expect(m.locator('h1')).to_have_text('VIONA')
    report['mobile_login_no_horizontal_overflow']=m.evaluate('() => document.documentElement.scrollWidth <= innerWidth')
    assert report['mobile_login_no_horizontal_overflow']
    browser.close()
(ROOT/'https-ui-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
