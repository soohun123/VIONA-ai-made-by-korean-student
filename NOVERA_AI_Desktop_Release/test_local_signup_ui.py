"""Hidden WebView2 registration/login integration; no physical input."""
import os,sys,time,json,secrets,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
out=ROOT/'artifacts/local-signup-ui';out.mkdir(parents=True,exist_ok=True)
os.environ['NOVERA_DATA_DIR']=str(out)
os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']='--disable-gpu'
sys.path.insert(0,str(ROOT/'src'))
import desktop,webview
original=webview.create_window
result={'passed':False,'physical_input_used':False}
def create(*args,**kwargs):
 kwargs['hidden']=True;kwargs['focus']=False
 window=original(*args,**kwargs);started=threading.Event()
 def drive(*ignored):
  if started.is_set():return
  started.set()
  try:
   deadline=time.monotonic()+20
   while not window.evaluate_js("typeof api!=='undefined'&&Boolean(api)"):
    if time.monotonic()>deadline:raise TimeoutError('bridge ready')
    time.sleep(.1)
   username='test_'+secrets.token_hex(5);password=secrets.token_urlsafe(18)
   window.evaluate_js("authMode(true)")
   result['form']=window.evaluate_js("({registerVisible:!document.getElementById('registerForm').hidden,loginHidden:document.getElementById('developerLoginForm').hidden,overflow:document.documentElement.scrollWidth>innerWidth})")
   js="document.getElementById('registerUsername').value="+json.dumps(username)+";document.getElementById('registerPassword').value="+json.dumps(password)+";document.getElementById('registerConfirm').value="+json.dumps(password)+";document.getElementById('registerForm').requestSubmit();true"
   window.evaluate_js(js)
   deadline=time.monotonic()+15
   while not window.evaluate_js("document.getElementById('authMessage').textContent.includes('회원가입이 완료')"):
    if time.monotonic()>deadline:raise TimeoutError('registration UI')
    time.sleep(.1)
   result['passwords_cleared']=window.evaluate_js("!document.getElementById('registerPassword').value&&!document.getElementById('registerConfirm').value")
   window.evaluate_js("document.getElementById('developerPassword').value="+json.dumps(password)+";document.getElementById('developerLoginForm').requestSubmit();true")
   deadline=time.monotonic()+15
   while not window.evaluate_js("typeof account!=='undefined'&&Boolean(account)"):
    if time.monotonic()>deadline:raise TimeoutError('login UI')
    time.sleep(.1)
   result['role']=window.evaluate_js('account.role')
   result['workspace_visible']=window.evaluate_js("!document.body.classList.contains('signed-out')")
   window.evaluate_js("document.getElementById('logout').click();true")
   deadline=time.monotonic()+10
   while not window.evaluate_js("document.body.classList.contains('signed-out')"):
    if time.monotonic()>deadline:raise TimeoutError('logout UI')
    time.sleep(.1)
   from System import Action
   from System.IO import MemoryStream
   from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
   stream=MemoryStream();tasks=[];view=window.native.webview
   view.Invoke(Action(lambda:tasks.append(view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,stream))))
   if not tasks[0].Wait(10000):raise TimeoutError('capture')
   (out/'login.png').write_bytes(bytes(stream.ToArray()));stream.Dispose()
   result['passed']=result['role']=='user' and result['passwords_cleared'] and result['workspace_visible'] and not result['form']['overflow']
  except Exception as e:result['error']=str(e)
  finally:
   (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');window.destroy()
 window.events.loaded+=drive
 return window
webview.create_window=create
sys.argv=[str(ROOT/'src/desktop.py')];desktop.main()
print(json.dumps(result,ensure_ascii=False))
if not result['passed']:raise SystemExit(1)
