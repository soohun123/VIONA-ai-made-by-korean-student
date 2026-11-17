"""Read-only server and worker resource trace across UI and HumanEval."""
import json,time,urllib.request
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
cache={}
with (ROOT/'benchmark-resources.jsonl').open('a',encoding='utf-8') as out:
    while True:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/status',timeout=5) as f:s=json.load(f)
            server_pid=next(c.pid for c in psutil.net_connections('tcp') if c.status=='LISTEN' and c.laddr.ip=='127.0.0.1' and c.laddr.port==8000)
            groups={}
            for label,pid in [('server',server_pid),('worker',s['worker_pid'])]:
                procs=[]
                if pid:
                    p=psutil.Process(pid);procs=[p]+(p.children(recursive=True) if label=='worker' else [])
                rows=[]
                for p in procs:
                    try:
                        if p.pid not in cache:cache[p.pid]=p;p.cpu_percent(None)
                        m=p.memory_info()
                        rows.append({'pid':p.pid,'rss':m.rss,'private':getattr(m,'private',None),'handles':p.num_handles(),'cpu_machine_percent':cache[p.pid].cpu_percent(None)/psutil.cpu_count()})
                    except psutil.Error:pass
                groups[label]=rows
            vm=psutil.virtual_memory()
            record={'time':time.time(),'status':s,'processes':groups,'available':vm.available,'used':vm.used}
            out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush()
            h=json.loads((ROOT/'humaneval/results.json').read_text(encoding='utf-8'))
            if h['completed']==164:break
        except Exception as e:
            out.write(json.dumps({'time':time.time(),'monitor_error':repr(e)})+'\n');out.flush()
        time.sleep(2)
