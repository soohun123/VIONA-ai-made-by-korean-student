"""Real local plugin CRUD through an isolated headless browser. Removes only its own plugin."""
import json,time,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
plugin_id='probe-'+uuid.uuid4().hex[:10]
result={'plugin_id':plugin_id,'checks':{},'errors':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000})
    page=context.new_page();page.on('pageerror',lambda error:result['errors'].append(str(error)))
    page.on('dialog',lambda dialog:dialog.accept())
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    expect(page.locator('#pluginSelect option[value="computer-use"]')).to_have_count(1)
    page.locator('#openPlugins').click();page.locator('#newPlugin').click()
    page.locator('#plugId').fill(plugin_id);page.locator('#plugName').fill('플러그인 검증용')
    page.locator('#plugInstructions').fill('한국어로 필요한 설명만 간결하게 답하세요.')
    page.locator('#plugRead').check();page.locator('#plugBudget').select_option('256')
    page.locator('#createPlugin').click()
    card=page.locator('[data-plugin-id="'+plugin_id+'"]')
    expect(card).to_be_visible();result['checks']['create']=True
    page.locator('#closePlugins').click();page.reload(wait_until='networkidle')
    expect(page.locator('#pluginSelect')).to_have_value(plugin_id)
    result['checks']['selection_persists']=True
    page.locator('#openPlugins').click();card=page.locator('[data-plugin-id="'+plugin_id+'"]')
    card.get_by_role('button',name='플러그인 검증용 켜기/끄기').click()
    expect(card.get_by_role('button',name='플러그인 검증용 켜기/끄기')).to_have_text('꺼짐')
    expect(card.get_by_role('button',name='대화에 사용')).to_be_disabled()
    result['checks']['disable']=True
    with page.expect_download() as download:card.get_by_role('button',name='내보내기',exact=True).click()
    exported=ROOT/'plugin-ui-export.json';download.value.save_as(str(exported))
    manifest=json.loads(exported.read_text(encoding='utf-8'))
    assert manifest['id']==plugin_id and manifest['capabilities']==['desktop.read']
    result['checks']['export']=True
    card.get_by_role('button',name='제거',exact=True).click();expect(card).to_have_count(0)
    page.locator('#pluginFile').set_input_files(str(exported))
    card=page.locator('[data-plugin-id="'+plugin_id+'"]');expect(card).to_be_visible()
    result['checks']['import']=True
    card.get_by_role('button',name='제거',exact=True).click();expect(card).to_have_count(0)
    result['checks']['own_probe_removed']=True
    page.screenshot(path=str(ROOT/'plugin-manager-desktop.png'))
    page.locator('#closePlugins').click();page.locator('#openSettings').click()
    expect(page.locator('#tokenProfile')).to_have_value('economy')
    page.locator('#memoryNotes').fill('프로젝트 목표를 유지해 줘.')
    page.locator('#memoryNotes').press('Tab')
    page.locator('#settingsDialog .close-dialog').click();page.reload(wait_until='networkidle')
    page.locator('#openSettings').click();expect(page.locator('#memoryNotes')).to_have_value('프로젝트 목표를 유지해 줘.')
    result['checks']['economy_default_and_pinned_memory']=True
    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    m=mobile.new_page();m.on('pageerror',lambda error:result['errors'].append(str(error)))
    m.goto('http://127.0.0.1:8000/mobile',wait_until='networkidle')
    m.locator('#menuToggle').click();m.locator('#openPlugins').click()
    expect(m.locator('[data-plugin-id="computer-use"]')).to_be_visible()
    assert m.evaluate('document.documentElement.scrollWidth<=innerWidth')
    m.screenshot(path=str(ROOT/'plugin-manager-mobile.png'))
    result['checks']['mobile_plugins']=True
    browser.close()
assert not result['errors'],result['errors']
(ROOT/'plugin-ui-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
