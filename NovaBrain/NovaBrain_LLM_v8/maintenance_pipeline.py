"""Continue only after the real-model soak succeeds; retain all benchmark samples."""
import json,time,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
while True:
    data=json.loads((ROOT/'stability-validation.json').read_text(encoding='utf-8'))
    if 'passed' in data:break
    time.sleep(5)
if not data['passed'] or data['elapsed_seconds']<600:raise SystemExit('Soak failed; benchmark not started')
for args in [['-m','unittest','test_memory_guard','-v'],['stop_local.py'],['launch_local.py']]:
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)
time.sleep(3)
subprocess.run([sys.executable,'test_ui_headless.py'],cwd=ROOT,check=True)
import psutil
from validate_install import get,chat
s=get('/status');root=psutil.Process(s['worker_pid'])
children=root.children(recursive=True)
native=next(p for p in children if p.name().lower()=='python.exe' and 'worker.py' in ' '.join(p.cmdline()))
assert Path(native.cwd()).resolve()==ROOT
native.terminate();native.wait(5);time.sleep(2)
reply=chat([{'role':'user','content':'7을 숫자로만 답해.'}],16)
recovery={'before':s,'terminated_native_pid':native.pid,'old_pids_surviving':[p.pid for p in [root,*children] if p.is_running()],'response':reply,'after':get('/status')}
(ROOT/'native-worker-recovery.json').write_text(json.dumps(recovery,ensure_ascii=False,indent=2),encoding='utf-8')
assert not recovery['old_pids_surviving'] and recovery['after']['ready']
print('UI_SUCCESS; STARTING_HUMANEVAL',flush=True)
subprocess.run([sys.executable,'humaneval_offline.py','--limit','164','--evaluate'],cwd=ROOT,check=True)
print('PIPELINE_COMPLETE',flush=True)
