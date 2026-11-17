"""Cancel own real image job, verify process cleanup and actual chat recovery."""
import json,time,urllib.request
from pathlib import Path
import psutil
from validate_install import get,chat
ROOT=Path(__file__).resolve().parent
token=get('/api/capabilities')['tool_token']
def post(path,data):
    req=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
job=post('/api/media/jobs',{'kind':'generate','prompt':'a red coffee cup on a white table','size':512,'steps':20,'seed':42,'translate':False,'plugin_id':'local-images'})
native=[];deadline=time.monotonic()+60
while time.monotonic()<deadline and not native:
    for proc in psutil.process_iter(['pid','cmdline','cwd']):
        args=proc.info['cmdline'] or []
        if args and Path(args[0]).name=='sd-cli.exe' and str(ROOT/'data/media/images'/(job['id']+'.png')) in args:
            native=[proc,*proc.children(recursive=True)]
    time.sleep(.2)
assert native,'Image subprocess not found'
time.sleep(2)
post('/api/media/jobs/'+job['id']+'/cancel',{})
deadline=time.monotonic()+60
while time.monotonic()<deadline:
    job=get('/api/media/jobs/'+job['id'])
    if job['state'] in ('done','error','cancelled'):break
    time.sleep(.5)
assert job['state']=='cancelled',job
assert all(not proc.is_running() for proc in native),'Native child remains'
reply=chat([{'role':'user','content':'Return only the sum: 19 + 23.'}],32)
assert '42' in reply['reply'],reply
result={'job':job,'native_pids':[p.pid for p in native],'all_native_processes_reaped':True,'actual_chat_recovery':reply,'status':get('/status')}
(ROOT/'local-media-cancel-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
