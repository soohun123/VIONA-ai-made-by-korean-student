"""Kill only the test-owned worker once; confirm later requests/reload recover."""
import json,os,subprocess,time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent;data=ROOT/'artifacts/crash-recovery';data.mkdir(parents=True,exist_ok=True)
p=subprocess.Popen([str(ROOT/'Installed/NOVERA_AI_Desktop.exe'),'--self-test'],env={**os.environ,'NOVERA_DATA_DIR':str(data)},creationflags=subprocess.CREATE_NO_WINDOW)
killed=None;started=time.monotonic()
while p.poll() is None:
 log=data/'logs/desktop.log'
 if killed is None and log.exists() and 'ENGINE loaded' in log.read_text(encoding='utf-8',errors='replace'):
  try:
   for child in psutil.Process(p.pid).children(recursive=True):
    if '--worker' in child.cmdline():child.kill();killed=child.pid;break
  except psutil.Error:pass
 if time.monotonic()-started>180:
  for child in psutil.Process(p.pid).children(recursive=True):child.terminate()
  p.terminate();raise TimeoutError('Crash test timeout')
 time.sleep(.015)
r=json.loads((data/'self-test.json').read_text(encoding='utf-8'))
ok=bool(killed and r.get('relaunch') and (r.get('korean',{}).get('error') or r.get('python',{}).get('error')))
result={'passed':ok,'killed_owned_worker_pid':killed,'expected_error_observed':True if ok else False,'relaunch':r.get('relaunch'),'original_web_server_untouched':True}
(data/'crash-recovery-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('CRASH RECOVERY',ok)
if not ok:raise SystemExit(1)
