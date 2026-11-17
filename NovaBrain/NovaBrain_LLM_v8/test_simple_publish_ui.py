import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
models=[dict(id='text-demo',name='VIONA 대화',kind='text',path='model.gguf',adapter='',domains=[],instructions='',enabled=True,publish=True),dict(id='image-demo',name='VIONA image1.5',kind='image',path='models/media/sd15-q4.gguf',adapter='',domains=[],instructions='',enabled=True,publish=False)]
calls=[];state={'fail':False};errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 page=b.new_page(viewport={'width':1280,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
 def handler(route):
  req=route.request;path=req.url.split('8000')[-1]
  if path=='/api/developer/models' and req.method=='GET':route.fulfill(json={'models':models,'releases':[],'files':['model.gguf']})
  elif path=='/api/developer/models' and req.method=='POST':calls.append(('save',req.post_data_json));route.fulfill(json={'ok':True})
  elif path=='/api/developer/publish':
   calls.append(('publish',req.post_data_json));route.fulfill(status=422 if state['fail'] else 200,json={'detail':'테스트용 실패'} if state['fail'] else {'id':'test-only','name':'test'})
  else:route.continue_()
 page.route('**/api/developer/**',handler)
 page.goto('http://127.0.0.1:8000/',wait_until='networkidle');page.locator('#openDeveloper').click()
 expect(page.locator('#publishModelChoices input')).to_have_count(2)
 assert not page.locator('#editModelPath').is_visible()
 page.locator('#publishModelChoices input[value="image-demo"]').check()
 page.locator('#publishModels').click();expect(page.locator('#developerStatus')).to_contain_text('배포 완료')
 assert calls[0][0]=='save' and calls[0][1]['publish'] is True
 assert calls[1][0]=='publish' and calls[1][1]['name'].startswith('VIONA')
 state['fail']=True;calls.clear();page.locator('#publishModelChoices input[value="image-demo"]').check();page.locator('#publishModels').click()
 expect(page.locator('#developerStatus')).to_contain_text('이전 배포는 유지')
 assert [c[0] for c in calls]==['save','publish','save'] and calls[-1][1]['publish'] is False
 page.screenshot(path=str(ROOT/'simple-publish-desktop.png'))
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(ROOT/'simple-publish-mobile.png'))
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 assert not errors,errors
 b.close()
(ROOT/'simple-publish-validation.json').write_text(json.dumps({'passed':True,'real_deployment_mutations':False,'checks':['selection','optional release name','advanced sections collapsed','publish success','failed publish restores draft flags','mobile overflow','no JS errors']},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS')
