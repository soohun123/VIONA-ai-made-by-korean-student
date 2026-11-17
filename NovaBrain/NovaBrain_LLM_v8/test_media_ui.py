"""Real local VLM through isolated headless UI; no user's pointer/browser profile."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
result={'checks':{},'errors':[],'network_requests':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1366,'height':900})
    page=context.new_page();page.on('pageerror',lambda e:result['errors'].append(str(e)))
    page.on('request',lambda r:result['network_requests'].append(r.url))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.locator('#mediaShortcut').click()
    page.locator('#imageFile').set_input_files(str(ROOT/'media-vision-fixture.png'))
    expect(page.locator('#inputImagePreview')).to_be_visible()
    page.locator('#translateMedia').uncheck()
    page.locator('#imageQuestion').fill('Describe the shapes and their colors briefly.')
    page.locator('#readImage').click()
    expect(page.locator('#cancelImageJob')).to_be_visible()
    expect(page.locator('#readImage')).to_be_enabled(timeout=90000)
    text=page.locator('#mediaResult p').inner_text()
    assert 'red' in text.lower() and 'blue' in text.lower(),text
    result['checks']['real_image_read']=text
    page.locator('#closeMedia').click()
    expect(page.locator('#log .message-image')).to_have_count(1)
    page.reload(wait_until='networkidle')
    expect(page.locator('#log .message-image')).to_have_count(1)
    result['checks']['image_history_survives_reload']=True
    page.locator('#pluginSelect').select_option('computer-use')
    page.locator('#prompt').fill('컴퓨터 사용');page.locator('#send').click()
    expect(page.locator('#desktopDialog')).to_be_visible()
    expect(page.locator('#send')).to_be_enabled()
    result['checks']['quiet_computer_use_opens_tool']=True
    page.locator('#desktopDialog .close-dialog').click()
    page.locator('#mediaShortcut').click();page.locator('#mediaGenerateTab').click()
    expect(page.locator('#imagePrompt')).to_be_visible()
    result['checks']['generation_controls']=True
    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    m=mobile.new_page();m.on('pageerror',lambda e:result['errors'].append(str(e)))
    m.goto('http://127.0.0.1:8000/mobile',wait_until='networkidle')
    m.locator('#mediaShortcut').click();m.locator('#mediaGenerateTab').click()
    expect(m.locator('#generateImage')).to_be_visible()
    assert m.evaluate('document.documentElement.scrollWidth<=innerWidth')
    result['checks']['mobile_controls_and_width']=True
    result['checks']['only_loopback_requests']=all(url.startswith('http://127.0.0.1:8000/') for url in result['network_requests'])
    browser.close()
assert not result['errors'],result['errors']
(ROOT/'media-ui-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))

