"""Real legacy continuation, PEFT continuation, version replacement and original preservation."""
import hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
from validate_install import get
ROOT=Path(__file__).resolve().parent;PARENT='2f9259f2187d4243bc86cb149bb77dfc'
dataset=next(d['id'] for d in get('/api/training')['datasets'] if d['id'].startswith('photos-') and d['name']=='누적 학습 검증 사진')
token=get('/api/capabilities')['tool_token']
def checksum(path):return hashlib.sha256(path.read_bytes()).hexdigest()
original=checksum(ROOT/'models/loras'/(PARENT+'.safetensors'))
def train(parent,steps,keep,replay):
    payload={'dataset_id':dataset,'name':'공공 유모차 누적 학습 검증','steps':steps,'resolution':128,'resume_adapter_id':parent,'keep_previous':keep,'replay_previous':replay}
    deadline=time.monotonic()+300
    while True:
        req=urllib.request.Request('http://127.0.0.1:8000/api/training/jobs',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:job=json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if exc.code!=409 or time.monotonic()>deadline:raise
            time.sleep(2)
    print('START',job['id'],keep,replay,flush=True);phase=None;deadline=time.monotonic()+660
    while time.monotonic()<deadline:
        job=get('/api/media/jobs/'+job['id'])
        if job['phase']!=phase:phase=job['phase'];print(phase,flush=True)
        if job['state'] in ('done','error','cancelled'):break
        time.sleep(2)
    (ROOT/('cumulative-preserve-job.json' if keep else 'cumulative-replace-job.json')).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
    assert job['state']=='done',job
    return job
parent=json.loads((ROOT/'models/loras'/(PARENT+'.json')).read_text(encoding='utf-8'))
first=train(PARENT,4,True,True);a=first['result']
assert a['initial_weight_hash']==parent['final_weight_hash'] and a['initial_weight_hash']!=a['final_weight_hash']
assert a['total_steps']==parent.get('total_steps',parent['steps'])+4 and a['version']==2
assert len(a['seen_dataset_counts'])==2,a
first_hash=checksum(ROOT/'models/loras'/(a['adapter_id']+'.safetensors'))
second=train(a['adapter_id'],2,False,False);b=second['result']
assert b['initial_weight_hash']==a['final_weight_hash'] and b['final_weight_hash']!=a['final_weight_hash']
assert b['adapter_id']==a['adapter_id'] and b['version']==3 and b['total_steps']==a['total_steps']+2
assert checksum(ROOT.parent/b['replaced_version_backup']/(a['adapter_id']+'.safetensors'))==first_hash
assert checksum(ROOT/'models/loras'/(PARENT+'.safetensors'))==original
result={'preserved':first,'replaced':second,'original_weights_unchanged':True,'replacement_backup_verified':True,'status':get('/status')}
(ROOT/'cumulative-live-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('CUMULATIVE_PASS',a['total_steps'],b['total_steps'],flush=True)
