"""Exercise deployed UI/bridge with hidden WebView2; no physical input/focus."""
import os,sys,time,json,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent;out=ROOT/'artifacts/web-ui-flow';out.mkdir(parents=True,exist_ok=True)
os.environ['NOVERA_DATA_DIR']=str(out);sys.path.insert(0,str(ROOT/'src'))
import desktop,webview
original=webview.create_window
result={'passed':False,'physical_input_used':False}
def create(*args,**kwargs):
 kwargs['hidden']=True;kwargs['focus']=False;kwargs['js_api']._user={'id':'developer','login':'integration-fixture','role':'developer'};result['authentication']='isolated developer-session fixture; no real login credentials used';window=original(*args,**kwargs);started=threading.Event()
 def drive(*ignored):
  if started.is_set():return
  started.set()
  try:
   deadline=time.monotonic()+10
   while not window.evaluate_js("Boolean(document.querySelector('#syncWeb')) && Boolean(typeof account!=='undefined'&&account)"):
    if time.monotonic()>deadline:raise TimeoutError('Application controls/auth fixture were not ready')
    time.sleep(.2)
   window.evaluate_js("show('settings');document.querySelector('#syncWeb').click()")
   deadline=time.monotonic()+90
   while window.evaluate_js('busy'):
    if time.monotonic()>deadline:raise TimeoutError('Web deployment import timeout')
    time.sleep(.2)
   result['deployment']=window.evaluate_js("({label:document.querySelector('#webRelease').textContent, model:document.querySelector('#model').value, imageModel:document.querySelector('#image_model').value})")
   window.evaluate_js("show('chat');document.querySelector('#prompt').value='한국어로 한 문장으로 인사해 줘.';document.querySelector('#chatForm').requestSubmit()")
   deadline=time.monotonic()+150
   while window.evaluate_js('busy'):
    if time.monotonic()>deadline:raise TimeoutError('UI chat timeout')
    time.sleep(.2)
   result['messages']=window.evaluate_js('current');saved=out/'accounts/developer-conversations.json';result['history_saved']=saved.exists() and any(h['messages'] and h['messages'][-1]==result['messages'][-1] for h in json.loads(saved.read_text(encoding='utf-8')))
   result['passed']=bool(result['deployment']['model'].startswith('web-') and result['messages'][-1]['role']=='assistant' and result['history_saved'])
  except Exception as e:
   result['error']=str(e)
   try:result['diagnostic']=window.evaluate_js("({url:location.href,title:document.title,ids:Array.from(document.querySelectorAll('[id]'),x=>x.id),api:typeof window.pywebview?.api,accountType:typeof account,auth:document.querySelector('#authMessage')?.textContent})")
   except Exception:pass
  finally:
   (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');window.destroy()
 window.events.loaded+=drive;return window
webview.create_window=create
sys.argv=[str(ROOT/'src/desktop.py')];desktop.main()
print('WEB UI FLOW',result['passed'])
if not result['passed']:raise SystemExit(1)
