"""Generate official HumanEval tasks through the local server; optional offline WASI evaluation.

One sample/task, no retries or repair. Full score is reported only for all 164.
WASI CPython differs from the upstream native evaluator; label results accordingly.
"""
import argparse,gzip,json,hashlib,textwrap,time
from pathlib import Path
from validate_install import chat
from sandbox_eval import Sandbox
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--limit',type=int,default=164)
parser.add_argument('--max-tokens',type=int,default=1024)
parser.add_argument('--evaluate',action='store_true',help='Execute only in offline WASI, never host Python')
args=parser.parse_args()
if not 1<=args.limit<=164:parser.error('--limit must be 1..164')
data=ROOT/'humaneval/HumanEval.jsonl.gz'
expected='b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef'
if hashlib.sha256(data.read_bytes()).hexdigest()!=expected:raise SystemExit('Dataset checksum mismatch')
tasks=[json.loads(line) for line in gzip.open(data,'rt',encoding='utf-8')]
out=ROOT/'humaneval/samples.jsonl'
existing={}
if out.exists():
    for line in out.read_text(encoding='utf-8').splitlines():
        obj=json.loads(line)
        if obj['task_id'] in existing:raise SystemExit('Duplicate task sample')
        existing[obj['task_id']]=obj
for task in tasks[:args.limit]:
    if task['task_id'] in existing:continue
    response=chat([{'role':'system','content':'Complete the Python function. Return only the missing indented function body. Do not repeat the function signature. No Markdown or explanation.'},{'role':'user','content':task['prompt']}],args.max_tokens)
    completion=response['reply']
    stripped=completion.strip()
    if stripped.startswith('```'):
        lines=stripped.splitlines()
        if lines[-1].strip()=='```':completion='\n'.join(lines[1:-1])+'\n'
    # Normalize indentation only. Never fix logic or retry failed samples.
    completion=textwrap.indent(textwrap.dedent(completion).strip('\n'),'    ')+'\n'
    sample={'task_id':task['task_id'],'completion':completion,'raw_response':response['reply'],'metrics':response['metrics']}
    with out.open('a',encoding='utf-8') as f:f.write(json.dumps(sample,ensure_ascii=False)+'\n')
    existing[task['task_id']]=sample
    print('Generated',task['task_id'],flush=True)
if args.evaluate:
    sandbox=Sandbox();results=[]
    for task in tasks[:args.limit]:
        sample=existing[task['task_id']]
        program=task['prompt']+sample['completion']+'\n'+task['test']+f"\ncheck({task['entry_point']})\nprint('HUMANEVAL_CHECK_PASSED')"
        checked=sandbox.run(program,timeout=10)
        checked['passed']=checked['passed'] and 'HUMANEVAL_CHECK_PASSED' in checked['output']
        results.append({'task_id':task['task_id'],**checked})
    report={'runtime':'CPython 3.11.4 WASI / Wasmtime; network disabled, read-only stdlib, 256 MiB, 10 seconds/task',
        'protocol':'one sample/task; temperature=0; seed=42; max_tokens='+str(args.max_tokens),
        'completed':len(results),'total':164,'passed':sum(x['passed'] for x in results),
        'full_humaneval_pass_at_1':sum(x['passed'] for x in results)/164 if len(results)==164 else None,
        'results':results}
    (ROOT/'humaneval/results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
else:print('Samples generated; execution not requested. No pass@1 measured.')
