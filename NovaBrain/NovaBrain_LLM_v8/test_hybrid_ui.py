"""Isolated headless UI checks with a fixture stream; no user's browser data/input touched."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
result={'browser':'isolated headless Edge','stream':'fixture (real model probes are separate)','checks':{},'errors':[]}
source={'title':'바나나','url':'https://ko.wikipedia.org/wiki/바나나','domain':'ko.wikipedia.org','snippet':'용어 설명'}
events=[{'kind':'context','sources':[source],'search_used':True,'skill_name':'출처 기반 용어 설명'}, {'token':'위키백과의 용어 설명입니다.\n\n바나나는 열매를 먹는 식물입니다. [1]'}, {'done':True,'metrics':{'output_tokens':0,'tokens_per_second':0}}]
body=''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':950})
    context.add_init_script("if(!localStorage.getItem('novabrain-v81-workspace'))localStorage.setItem('novabrain-v8-history',JSON.stringify([{role:'user',content:'이전 기록 보존 테스트'},{role:'assistant',content:'이전 답변'}]));")
    page=context.new_page();page.on('pageerror',lambda e:result['errors'].append(str(e)))
    page.route('**/chat/stream',lambda route:route.fulfill(status=200,content_type='application/x-ndjson',body=body))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    assert '이전 답변' in page.locator('#log').inner_text()
    result['checks']['legacy_migration']=True
    page.locator('#newChat').click();page.locator('#prompt').fill('바나나');page.locator('#send').click()
    expect(page.locator('#send')).to_be_enabled()
    assert page.locator('.source-card').count()==1
    page.reload(wait_until='networkidle');assert page.locator('.source-card').count()==1
    result['checks']['sources_persist_after_reload']=True
    assert page.evaluate("JSON.parse(localStorage.getItem('novabrain-v8-history'))[0].content")== '이전 기록 보존 테스트'
    result['checks']['legacy_original_unchanged']=True
    assert page.locator('.chat-item').count()==2
    result['checks']['multiple_chats']=True
    with page.expect_download() as download:page.locator('#export').click()
    download.value.save_as(str(ROOT/'hybrid-ui-export.json'))
    assert len(json.loads((ROOT/'hybrid-ui-export.json').read_text(encoding='utf-8')))==2
    result['checks']['export']=True
    page.locator('#modelButton').click();expect(page.locator('#gpuMode')).to_have_value('hybrid')
    result['checks']['hybrid_setting_selected']=True
    page.screenshot(path=str(ROOT/'hybrid-settings.png'))
    page.locator('[data-tab=general]').click();page.locator('#themeSelect').select_option('light')
    assert page.locator('html').get_attribute('data-theme')=='light'
    page.locator('#themeSelect').select_option('dark')
    result['checks']['themes']=True
    page.locator('#settingsDialog .close-dialog').click()
    page.screenshot(path=str(ROOT/'hybrid-desktop.png'))
    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    m=mobile.new_page();m.on('pageerror',lambda e:result['errors'].append(str(e)))
    m.route('**/chat/stream',lambda route:route.fulfill(status=200,content_type='application/x-ndjson',body=body))
    m.goto('http://127.0.0.1:8000/mobile',wait_until='networkidle')
    assert m.evaluate('document.documentElement.scrollWidth<=innerWidth')
    m.locator('#prompt').fill('바나나');m.locator('#send').click();expect(m.locator('#send')).to_be_enabled()
    assert m.locator('.source-card').count()==1
    m.screenshot(path=str(ROOT/'hybrid-mobile.png'))
    result['checks']['mobile_layout_and_stream']=True
    browser.close()
assert not result['errors'],result['errors']
(ROOT/'hybrid-ui-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
