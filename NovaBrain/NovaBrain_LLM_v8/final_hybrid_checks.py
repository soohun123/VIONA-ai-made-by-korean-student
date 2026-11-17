import json,time,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
while True:
    data=json.loads((ROOT/'hybrid-validation.json').read_text(encoding='utf-8'))
    if 'passed' in data:break
    time.sleep(3)
if not data['passed'] or data['elapsed_seconds']<600:raise SystemExit('Hybrid soak failed')
for args in [['stop_local.py'],['launch_local.py']]:
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)
time.sleep(2)
subprocess.run([sys.executable,'verify_random_words.py','--output','random-words-final.json'],cwd=ROOT,check=True)
subprocess.run([sys.executable,'test_hybrid_ui.py'],cwd=ROOT,check=True)
from validate_install import get,chat
smoke=chat([{'role':'user','content':'파이썬에서 두 수를 더하는 add(a, b) 함수를 코드만 작성해 줘.'}],128)
status=get('/status');gpu=get('/api/gpu')
assert status['ready'] and status['placement']['cpu_blocks']==14 and status['placement']['gpu_blocks']==14
assert status['errors']==0
(ROOT/'hybrid-final-smoke.json').write_text(json.dumps({'response':smoke,'status':status,'gpu':gpu},ensure_ascii=False,indent=2),encoding='utf-8')
subprocess.run([sys.executable,'write_hybrid_report.py'],cwd=ROOT,check=True)
print('FINAL_HYBRID_CHECKS_COMPLETE',flush=True)
