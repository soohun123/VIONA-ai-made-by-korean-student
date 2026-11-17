"""Compare actual native baseline and trained-adapter generation with identical seed/conditions."""
import argparse,hashlib,json,time,urllib.request
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
from validate_install import get
ROOT=Path(__file__).resolve().parent
adapter=json.loads((ROOT/'public-photo-training-validation.json').read_text(encoding='utf-8'))['result']['adapter_id']
parser=argparse.ArgumentParser();parser.add_argument('--quality',action='store_true');quality=parser.parse_args().quality
token=get('/api/capabilities')['tool_token']
def generate(adapter_id):
    payload={'kind':'generate','prompt':('a baby stroller with four wheels and a canopy, product photography' if quality else 'a photograph of a stroller standing on a sidewalk, daylight'),'size':512 if quality else 256,'steps':20 if quality else 8,'seed':42 if quality else 777,'translate':False,'adapter_id':adapter_id,'adapter_strength':0.3 if quality else 0.7}
    req=urllib.request.Request('http://127.0.0.1:8000/api/media/jobs',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
    with urllib.request.urlopen(req,timeout=30) as r:job=json.load(r)
    print('START',adapter_id or 'baseline',job['id'],flush=True)
    deadline=time.monotonic()+660
    while time.monotonic()<deadline:
        job=get('/api/media/jobs/'+job['id'])
        if job['state'] in ('done','error','cancelled'):break
        time.sleep(1)
    (ROOT/(('quality-' if quality else '')+('trained-adapter-job.json' if adapter_id else 'trained-baseline-job.json'))).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
    assert job['state']=='done',job
    return job
baseline=generate('');trained=generate(adapter)
paths=[ROOT/'data/media/images'/(j['result']['image_id']+'.png') for j in (baseline,trained)]
with Image.open(paths[0]) as a,Image.open(paths[1]) as b:
    a=a.convert('RGB');b=b.convert('RGB');hashes=[hashlib.sha256(x.tobytes()).hexdigest() for x in (a,b)]
    difference=ImageStat.Stat(ImageChops.difference(a,b)).mean
assert hashes[0]!=hashes[1], 'Adapter did not change rendered RGB pixels'
result={'baseline':baseline,'trained':trained,'rgb_sha256':hashes,'mean_absolute_rgb_difference':difference,'status':get('/status')}
(ROOT/('photo-trained-generation-quality-validation.json' if quality else 'photo-trained-generation-validation.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('APPLIED',hashes,difference,flush=True)
