"""Headless UI with real account/role bridge and fixture model operations only."""
import functools,http.server,json,secrets,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import desktop
from local_accounts import password_hash

ROOT=Path(__file__).resolve().parents[1]

def main():
    from playwright.sync_api import sync_playwright,expect
    output=ROOT/'artifacts/accounts-ui';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        data=Path(temporary);(data/'assets').mkdir();password=secrets.token_urlsafe(20)
        (data/'assets/developer-account.json').write_text(json.dumps({'login':'soo_dev','password_hash':password_hash(password)}))
        ctl=Mock();ctl.lock=threading.Lock();ctl.cancel.return_value={'ok':True}
        ctl.status.return_value={'phase':'준비됨','ready':False,'free_gib':8,'used_gib':7,'gpu':{'name':'테스트 장치','free_mib':2000},'loaded':None,'error':''}
        settings={'mode':'cpu','threads':3,'context':8192,'model':'fixture','image_model':'image','adapter':'','strength':.3,'text_lora':True,'follow_web':True}
        ctl.bootstrap.side_effect=lambda:{'history':[],'settings':settings,'models':[{'id':'fixture','kind':'text','name':'테스트 대화 모델'},{'id':'image','kind':'image','name':'테스트 이미지 모델'}],'adapters':[],'web_release':None}
        with patch.object(desktop,'DATA',data),patch.object(desktop,'BUNDLE',data):bridge=desktop.Bridge(ctl)
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'assets')))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        results=[]
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
                for width in (1180,800):
                    bridge.logout();context=browser.new_context(viewport={'width':width,'height':950});page=context.new_page();errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.expose_function('nativeCall',lambda name,args:getattr(bridge,name)(*args))
                    page.add_init_script("window.pywebview={api:new Proxy({},{get:(target,key)=>(...args)=>window.nativeCall(key,args)})};window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));")
                    page.goto(f'http://127.0.0.1:{server.server_port}/index.html',wait_until='networkidle')
                    expect(page.locator('#authScreen')).to_be_visible();expect(page.locator('aside')).not_to_be_visible()
                    expect(page.locator('#googleLogin')).to_be_disabled();expect(page.locator('#naverLogin')).to_be_disabled()
                    page.screenshot(path=str(output/f'login-{width}.png'))
                    page.locator('.developer-login summary').click();page.locator('#developerPassword').fill('incorrect')
                    page.locator('#developerSignIn').click();expect(page.locator('#authMessage')).to_contain_text('확인')
                    page.locator('#developerPassword').fill(password);page.locator('#developerSignIn').click()
                    expect(page.locator('#accountName')).to_have_text('soo_dev · 개발자');expect(page.locator('#authScreen')).not_to_be_visible()
                    page.locator('[data-pane=developer]').click();expect(page.locator('#developer')).to_be_visible()
                    page.locator('#oauthProvider').select_option('naver');expect(page.locator('#oauthCallback')).to_contain_text('43871/oauth/callback/naver')
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    page.screenshot(path=str(output/f'developer-{width}.png'))
                    page.locator('#logout').click();expect(page.locator('#authScreen')).to_be_visible()
                    bridge._social_identity('google',{'sub':f'fixture-{width}','name':'일반 사용자','email':'fixture@example.com','email_verified':True})
                    expect(page.locator('#accountName')).to_have_text('일반 사용자',timeout=5000)
                    expect(page.locator('[data-pane=developer]')).not_to_be_visible();expect(page.locator('[data-pane=logs]')).not_to_be_visible()
                    page.locator('[data-pane=settings]').click();expect(page.locator('#addModel')).not_to_be_visible()
                    assert bridge.sync_web()['code']=='developer_required'
                    assert not errors,errors
                    results.append({'width':width,'login_and_logout':True,'developer_settings':True,'user_cannot_access_developer':True,'unconfigured_social_disabled':True,'errors':errors})
                    context.close()
                browser.close()
        finally:bridge.logout();server.shutdown();server.server_close()
        (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
