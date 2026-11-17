"""Hidden native WebView2 render test with owned-tree memory/listener sampling."""
import json,os,subprocess,time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent;data=ROOT/'artifacts/shipping-gui';data.mkdir(parents=True,exist_ok=True)
p=subprocess.Popen([str(ROOT/'Installed/NOVERA_AI_Desktop.exe'),'--gui-smoke'],env={**os.environ,'NOVERA_DATA_DIR':str(data)},creationflags=subprocess.CREATE_NO_WINDOW)
samples=[];listeners=[];start=time.monotonic()
while p.poll() is None:
 if time.monotonic()-start>120:
  for child in psutil.Process(p.pid).children(recursive=True):child.terminate()
  p.terminate();raise TimeoutError('GUI timeout')
 try:
  tree=[psutil.Process(p.pid)]+psutil.Process(p.pid).children(recursive=True);samples.append({'time':time.time(),'rss_gib':sum(x.memory_info().rss for x in tree)/2**30})
  for item in tree:
   try:
    for c in item.net_connections(kind='inet'):
     if c.status==psutil.CONN_LISTEN:listeners.append({'pid':item.pid,'ip':c.laddr.ip,'port':c.laddr.port})
   except psutil.Error:pass
 except psutil.Error:pass
 time.sleep(.3)
result=json.loads((data/'gui-smoke.json').read_text(encoding='utf-8'));result.update(peak_gui_tree_rss_gib=max((x['rss_gib'] for x in samples),default=0),listeners=listeners,external_listeners_found=any(x['ip'] not in ['127.0.0.1','::1'] for x in listeners))
(data/'gui-resource-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('GUI',result.get('ok'),'RAM',result['peak_gui_tree_rss_gib'],'external_listener',result['external_listeners_found'])
if not result.get('ok') or result['external_listeners_found']:raise SystemExit(1)
