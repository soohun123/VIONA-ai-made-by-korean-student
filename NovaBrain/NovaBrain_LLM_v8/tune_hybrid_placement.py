"""Measure public llama.cpp offload configurations; retain CPU and GPU model work."""
import json,time,urllib.request,statistics
from pathlib import Path
from validate_install import chat,get
ROOT=Path(__file__).resolve().parent
token=get('/api/capabilities')['tool_token']
def configure(blocks):
    request=urllib.request.Request('http://127.0.0.1:8000/api/runtime',data=json.dumps({'gpu_mode':'hybrid','gpu_blocks':blocks}).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
    with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
prompts=['Write only a Python binary_search(numbers, target) function. Return -1 when absent.','Write only a Python function that counts word frequencies in a string.']
results=[]
for blocks in (14,20,24,26):
    item={'requested_gpu_blocks':blocks,'responses':[]}
    try:
        configure(blocks);time.sleep(.5)
        chat([{'role':'user','content':'Return only Python code for add(a,b).'}],64)
        for prompt in prompts:item['responses'].append(chat([{'role':'user','content':prompt}],128))
        status=get('/status');gpu=get('/api/gpu')
        item.update({'placement':status['placement'],'gpu':gpu,'status':status})
        item['tokens_per_second']=sum(r['metrics']['output_tokens'] for r in item['responses'])/sum(r['metrics']['elapsed_seconds'] for r in item['responses'])
        item['eligible']=status['placement']['gpu_blocks']==blocks and status['placement']['cpu_blocks']>=2 and gpu['free_mib']>=500 and status['error'] is None
    except Exception as e:item['error']=repr(e);item['eligible']=False
    results.append(item);(ROOT/'placement-tuning.json').write_text(json.dumps({'candidates':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(blocks,item.get('tokens_per_second'),item['eligible'],item.get('error'),flush=True)
eligible=[r for r in results if r['eligible']]
if not eligible:raise RuntimeError('No safe measured candidate; inspect report')
winner=max(eligible,key=lambda r:r['tokens_per_second'])
configure(winner['requested_gpu_blocks'])
chat([{'role':'user','content':'Return only Python code for add(a,b).'}],64)
report={'candidates':results,'selected_gpu_blocks':winner['requested_gpu_blocks'],'baseline_tokens_per_second':results[0].get('tokens_per_second'),'selected_tokens_per_second':winner['tokens_per_second'],'gain_percent':100*(winner['tokens_per_second']/results[0]['tokens_per_second']-1),'final_status':get('/status')}
(ROOT/'placement-tuning.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('candidates','final_status')},indent=2))
