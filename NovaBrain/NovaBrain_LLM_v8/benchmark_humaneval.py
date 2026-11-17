"""Generate HumanEval samples. Never executes model-produced code."""
import argparse, json, time, urllib.request, urllib.error
from pathlib import Path
from human_eval.data import read_problems
p=argparse.ArgumentParser()
p.add_argument('--url',default='http://127.0.0.1:8000')
p.add_argument('--out',default='humaneval_samples.jsonl')
p.add_argument('--limit',type=int,default=164)
p.add_argument('--max-tokens',type=int,default=1024)
p.add_argument('--temperature',type=float,default=0.0)
a=p.parse_args()
if not 1<=a.limit<=164: p.error('limit must be 1..164')
problems=read_problems()
items=list(problems.items())[:a.limit]
out=Path(a.out)
completed=set()
if out.exists():
 for line in out.read_text(encoding='utf-8').splitlines():
  try: completed.add(json.loads(line)['task_id'])
  except (ValueError,KeyError): pass
for i,(task_id,problem) in enumerate(items,1):
 if task_id in completed: continue
 prompt=problem['prompt']
 # Force completion-only to preserve HumanEval entry point and signature.
 messages=[{'role':'system','content':'You are a Python coding assistant. Complete the supplied Python function. Return only Python source code for the function body, without Markdown fences or explanations. Do not repeat the function signature.'}, {'role':'user','content':'Complete the following Python function. Output only the missing indented function body.\n\n'+prompt}]
 payload={'messages':messages,'max_tokens':a.max_tokens,'temperature':a.temperature,'top_p':1.0}
 req=urllib.request.Request(a.url.rstrip('/')+'/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
 parts=[]; start=time.monotonic()
 try:
  with urllib.request.urlopen(req,timeout=900) as response:
   for raw in response:
    obj=json.loads(raw)
    if obj.get('error'): raise RuntimeError(obj['error'])
    parts.append(obj.get('token',''))
 except (urllib.error.URLError,RuntimeError) as exc:
  print('FAILED',task_id,exc,flush=True);break
 completion=''.join(parts).strip()
 if completion.startswith('```'):
  lines=completion.splitlines();completion='\n'.join(lines[1:-1]) if len(lines)>2 and lines[-1].strip()=='```' else completion
 # The canonical benchmark concatenates prompt+completion; strip leading duplicate def if present.
 if completion.lstrip().startswith(('def ','async def ')):
  print('WARNING: model returned full function for',task_id,'; sample may fail')
 with out.open('a',encoding='utf-8') as f:
  f.write(json.dumps({'task_id':task_id,'completion':completion},ensure_ascii=False)+'\n')
 print(f'{i}/{len(items)} {task_id} {time.monotonic()-start:.1f}s',flush=True)
print('Samples:',out,'Completed:',len(completed)+sum(1 for x in out.read_text(encoding='utf-8').splitlines() if json.loads(x)['task_id'] not in completed))
