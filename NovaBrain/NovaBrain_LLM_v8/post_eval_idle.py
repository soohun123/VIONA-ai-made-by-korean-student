"""Observe the same worker for two minutes after all evaluation, without generation."""
import json,time,statistics
from pathlib import Path
import psutil
from validate_install import get
ROOT=Path(__file__).resolve().parent
s=get('/status');pid=s['worker_pid'];restarts=s['restarts'];rows=[]
root=psutil.Process(pid);procs=[root]+root.children(recursive=True)
for p in procs:p.cpu_percent(None)
start=time.monotonic()
while True:
    status=get('/status');total={'rss':0,'private':0,'handles':0,'cpu_machine_percent':0}
    for p in procs:
        m=p.memory_info();total['rss']+=m.rss;total['private']+=getattr(m,'private',0)
        total['handles']+=p.num_handles();total['cpu_machine_percent']+=p.cpu_percent(None)/psutil.cpu_count()
    rows.append({'time':time.time(),'status':status,**total})
    assert status['worker_pid']==pid and status['ready'] and status['restarts']==restarts
    if time.monotonic()-start>=125:break
    time.sleep(1)
r={'seconds':time.monotonic()-start,'worker_pid':pid,'passed':True,'samples':rows,'summary':{k:{'start':rows[0][k],'max':max(x[k] for x in rows),'end':rows[-1][k],'mean':statistics.mean(x[k] for x in rows)} for k in total}}
(ROOT/'post-eval-idle.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in r.items() if k!='samples'},indent=2))
