"""Real-model 10 minute soak. Never executes model-generated code."""
import json,time,threading,urllib.request,statistics
from pathlib import Path
import psutil
from validate_install import chat,get
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'hybrid-validation.json'
result={'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'requests':[],'events':[],'samples':[]}
done=threading.Event();cache={}
server_pid=next(c.pid for c in psutil.net_connections('tcp') if c.status=='LISTEN' and c.laddr.port==8000 and c.laddr.ip=='127.0.0.1')
def post(path):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000'+path,data=b'{}'),timeout=30) as r:return json.load(r)
def tree(pid):
    if not pid:return []
    try:return [psutil.Process(pid)]+psutil.Process(pid).children(recursive=True)
    except psutil.Error:return []
def measure(procs):
    values={'rss':0,'private':0,'handles':0,'cpu_machine_percent':0,'threads':0,'pids':[]}
    for p in procs:
        try:
            if p.pid not in cache:cache[p.pid]=p;p.cpu_percent(None)
            m=p.memory_info();values['rss']+=m.rss;values['private']+=getattr(m,'private',0)
            values['handles']+=p.num_handles();values['threads']+=p.num_threads()
            values['cpu_machine_percent']+=cache[p.pid].cpu_percent(None)/psutil.cpu_count()
            values['pids'].append(p.pid)
        except psutil.Error:pass
    return values
def save():OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
def monitor():
    while not done.is_set():
        try:
            s=get('/status');worker=tree(s['worker_pid']);worker_ids={p.pid for p in worker}
            server=[p for p in tree(server_pid) if p.pid not in worker_ids]
            vm=psutil.virtual_memory()
            result['samples'].append({'time':time.time(),'worker_pid':s['worker_pid'],'ready':s['ready'],'server':measure(server),'worker':measure(worker),'available':vm.available,'used':vm.used,'restarts':s['restarts'],'errors':s['errors']})
        except Exception as e:result['events'].append({'monitor_error':repr(e)})
        done.wait(1)
def request(prompt='파이썬에서 이진 탐색 함수를 작성하고 한국어로 간단히 설명해 줘.',tokens=128):
    r=chat([{'role':'user','content':prompt}],tokens)
    result['requests'].append({'time':time.time(),**r});save()
    print('completed',len(result['requests']),flush=True)
def interrupt(kind):
    before=get('/status');old=tree(before['worker_pid'])
    payload={'messages':[{'role':'user','content':'파이썬 정렬 알고리즘 10개를 코드와 함께 아주 길게 설명해 줘.'}],'max_tokens':1024,'temperature':0,'top_p':1}
    req=urllib.request.Request('http://127.0.0.1:8000/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:
        for line in r:
            if json.loads(line).get('token'):break
        if kind=='cancel':post('/admin/cancel');r.read()
    deadline=time.monotonic()+15
    while get('/status')['ready'] and time.monotonic()<deadline:time.sleep(.2)
    time.sleep(1)
    alive=[p.pid for p in old if p.is_running()]
    assert not alive,(kind,alive)
    result['events'].append({'kind':kind,'old_pids':[p.pid for p in old],'survivors':alive})
    request('2+5는? 숫자만 답해.',16)
start=time.monotonic()
try:
    request('파이썬 리스트를 한국어 한 문장으로 설명해 줘.',64)
    result['initial_status']=get('/status')
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    for kind in ['cancel','disconnect','cancel','disconnect']:
        interrupt(kind)
    old=tree(get('/status')['worker_pid']);launcher=old[0]
    assert Path(launcher.cwd()).resolve()==ROOT and 'worker.py' in ' '.join(launcher.cmdline())
    launcher.terminate();launcher.wait(5)
    time.sleep(3)
    survivors=[p.pid for p in old if p.is_running()]
    assert not survivors,survivors
    result['events'].append({'kind':'launcher_crash','old_pids':[p.pid for p in old],'survivors':survivors})
    request('3+4는? 숫자만 답해.',16)
    while time.monotonic()-start<605:
        request(tokens=256 if len(result['requests'])%4==0 else 128)
        time.sleep(6)
    result['final_status']=get('/status');result['elapsed_seconds']=time.monotonic()-start
    result['passed']=result['final_status']['ready'] and result['final_status']['errors']==0 and result['final_status'].get('placement',{}).get('gpu_blocks')==14 and result['final_status'].get('placement',{}).get('cpu_blocks')==14
except Exception as e:
    result['fatal_error']=repr(e);result['passed']=False;raise
finally:
    done.set()
    if 'thread' in globals():thread.join(15)
    result['elapsed_seconds']=time.monotonic()-start
    save()
    print(json.dumps({k:v for k,v in result.items() if k not in ('requests','samples')},ensure_ascii=True),flush=True)
