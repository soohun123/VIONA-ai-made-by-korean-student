"""Exercise local image generation/reading and monitor until completion."""
import argparse,base64,json,time,urllib.request
from pathlib import Path
from PIL import Image,ImageDraw
from validate_install import get
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['read','generate']);args=parser.parse_args()
token=get('/api/capabilities')['tool_token']
def post(path,body):
    request=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
    with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
payload={'kind':args.kind,'translate':False,'plugin_id':'local-images'}
if args.kind=='read':
    fixture=ROOT/'media-vision-fixture.png'
    image=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(image);draw.rectangle((35,70,170,230),fill='red');draw.ellipse((210,120,335,245),fill='blue');image.save(fixture)
    upload=post('/api/media/upload',{'data_url':'data:image/png;base64,'+base64.b64encode(fixture.read_bytes()).decode()})
    payload.update({'image_id':upload['id'],'prompt':'Describe the shapes and their colors in this image.'})
else:payload.update({'prompt':'a small red robot reading a book, simple clean illustration, white background','size':384,'steps':12,'seed':42})
job=post('/api/media/jobs',payload);print('JOB',job['id'],flush=True)
started=time.monotonic();last_phase=None
while time.monotonic()-started<660:
    job=get('/api/media/jobs/'+job['id'])
    if job['phase']!=last_phase:print(job['phase'],flush=True);last_phase=job['phase']
    if job['state'] in ('done','error','cancelled'):break
    time.sleep(2)
report={'job':job,'status':get('/status'),'gpu':get('/api/gpu')}
(ROOT/('local-media-'+args.kind+'-validation.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2),flush=True)
if job['state']!='done':raise SystemExit(1)
