"""Real headless UI: detailed generation, allocation controls, filter settings and mobile LoRA."""
import json,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from validate_install import get,chat
ROOT=Path(__file__).resolve().parent
cap=get('/api/capabilities');token=cap['tool_token'];original=cap['runtime'];safety=get('/api/content-filter')
def post(path,body):
    req=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
result={'checks':{},'errors':[]}
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1366,'height':950})
        page=context.new_page();page.on('pageerror',lambda e:result['errors'].append(str(e)))
        page.goto('http://127.0.0.1:8000',wait_until='networkidle')
        page.locator('#openSettings').click();page.locator('#responseStyle').select_option('detailed')
        expect(page.locator('#tokenProfile')).to_have_value('full');expect(page.locator('#maxTokens')).to_have_value('2048')
        page.locator('[data-tab=tools]').click();page.locator('#searchMode').select_option('off')
        page.locator('#settingsDialog .close-dialog').click();page.reload(wait_until='networkidle')
        page.locator('#openSettings').click();expect(page.locator('#responseStyle')).to_have_value('detailed')
        result['checks']['detailed_style_persists_and_reserves_tokens']=True
        page.locator('[data-tab=model]').click();page.locator('#gpuMode').select_option('hybrid')
        page.locator('#gpuBlocks').evaluate("el=>{el.value='14';el.dispatchEvent(new Event('input',{bubbles:true}))}")
        expect(page.locator('#gpuBlocksLabel')).to_have_text('CPU 14 / GPU 14')
        with page.expect_response('**/api/runtime') as response:page.locator('#applyGpu').click()
        assert response.value.ok
        page.locator('#settingsDialog .close-dialog').click()
        prompt='파이썬 딕셔너리가 무엇인지, 리스트와 차이, 조회·추가·수정 예시를 초보자가 이해하도록 설명해 줘.'
        page.locator('#prompt').fill(prompt)
        with page.expect_request('**/chat/stream') as request:page.locator('#send').click()
        result['detailed_payload']=request.value.post_data_json
        expect(page.locator('#send')).to_be_enabled(timeout=180000)
        reply=page.locator('.message.assistant .message-body').last.inner_text();assert len(reply)>400,reply
        result['detailed_reply']=reply;status=get('/status');result['detailed_metrics']=status['last_metrics']
        assert status['placement']['cpu_blocks']==14 and status['placement']['gpu_blocks']==14,status
        result['checks']['real_14_14_allocation_and_detailed_model_reply']=True
        print('DETAILED_OK',len(reply),flush=True)
        page.locator('#openSettings').click();page.locator('[data-tab=tools]').click()
        page.locator('#filterPrivacy').uncheck();page.locator('#saveContentFilter').click()
        expect(page.locator('#filterStatus')).to_contain_text('저장됨');assert not get('/api/content-filter')['privacy']
        page.locator('#filterPrivacy').check()
        with page.expect_response('**/api/content-filter') as saved:page.locator('#saveContentFilter').click()
        assert saved.value.ok and get('/api/content-filter')['privacy']
        expect(page.locator('#filterStatus')).to_contain_text('저장됨')
        result['checks']['filter_ui_saves_server_settings']=True
        page.locator('#settingsDialog .close-dialog').click();page.locator('#openTraining').click()
        expect(page.locator('#trainingDataset option[value="daejeon-strollers"]')).to_have_count(1)
        assert '200장' in page.locator('#trainingDataset').inner_text()
        page.screenshot(path=str(ROOT/'photo-training-desktop.png'))
        result['checks']['public_dataset_and_training_controls']=True
        mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        m=mobile.new_page();m.on('pageerror',lambda e:result['errors'].append(str(e)))
        m.goto('http://127.0.0.1:8000/mobile',wait_until='networkidle')
        m.locator('#menuToggle').click();m.locator('#openTraining').click()
        expect(m.locator('#startTraining')).to_be_visible();assert m.evaluate('document.documentElement.scrollWidth<=innerWidth')
        m.screenshot(path=str(ROOT/'photo-training-mobile.png'));m.locator('#closeTraining').click()
        m.locator('#mediaShortcut').click();m.locator('#mediaGenerateTab').click()
        expect(m.locator('#activeLora option')).to_have_count(2)
        result['checks']['mobile_training_and_lora_selection']=True
        browser.close()
finally:
    post('/api/runtime',original)
    post('/api/content-filter',{k:safety[k] for k in ('privacy','sexual','violence','image_threshold')})
    result['restored_chat']=chat([{'role':'user','content':'Return only the sum: 19 + 23.'}],32)
    result['final_status']=get('/status')
    (ROOT/'training-controls-ui-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
assert not result['errors'],result['errors']
print(json.dumps({'checks':result['checks'],'errors':result['errors']},ensure_ascii=True,indent=2))
