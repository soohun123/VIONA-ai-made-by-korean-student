"""Offline serial curriculum; immutable new runs, no automatic activation."""
import os,json,time,datetime,subprocess,hashlib
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
OUT=Path(json.loads((ROOT/'data/text-training/latest-curriculum.json').read_text())['directory'])
STATUS=OUT/'training-status.json'
def save(report):
 tmp=STATUS.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 for i in range(30):
  try:tmp.replace(STATUS);return
  except PermissionError:time.sleep(.1)
 raise RuntimeError('Status write failed')
def main():
 owner=psutil.Process();report={'state':'starting','pid':os.getpid(),'process_created':owner.create_time(),'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'target_training_seconds_per_topic':1800,'topics':[],'activated':False,'quality_gain_measured':False}
 save(report)
 resume=ROOT/'data/text-training/runs/87431fd2a461424aa3fd1721107bde41/adapter'
 if not (resume/'adapter_config.json').exists():raise RuntimeError('Existing trainable adapter missing')
 for topic in ['security','coding','html']:
  part={'topic':topic,'state':'waiting','runs':[],'actual_training_seconds':0,'optimizer_steps':0};report['topics'].append(part)
  for segment in range(3):
   report.update(state='waiting_for_ram',current_topic=topic,segment=segment+1);save(report)
   deadline=time.monotonic()+600
   while psutil.virtual_memory().available<9*2**30:
    if (OUT/'cancel').exists():report['state']='cancelled';save(report);return
    if time.monotonic()>deadline:report.update(state='blocked',reason='9 GiB free RAM was not available within 10 minutes');save(report);return
    time.sleep(5)
   before=set((ROOT/'data/text-training/runs').iterdir())
   cmd=[str(ROOT/'.training-venv/Scripts/python.exe'),str(ROOT/'train_qwen_lora.py'),'--seconds','600','--fast-cpu','--lean-embedding','--corpus',str(OUT/(topic+'.jsonl')),'--resume',str(resume)]
   with (OUT/(topic+'-'+str(segment+1)+'.log')).open('w',encoding='utf-8') as log:
    child=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'},creationflags=subprocess.CREATE_NO_WINDOW)
    report.update(state='training',child_pid=child.pid);part['state']='training';save(report)
    started=time.monotonic()
    while child.poll() is None:
     if (OUT/'cancel').exists() or time.monotonic()-started>1200:
      child.terminate();child.wait(timeout=10);report.update(state='cancelled' if (OUT/'cancel').exists() else 'failed',reason='Owned training process stopped; prior completed segments retained');save(report);return
     time.sleep(2)
   new=set((ROOT/'data/text-training/runs').iterdir())-before
   if len(new)!=1:report.update(state='failed',reason='Cannot uniquely identify new training result');save(report);return
   run=new.pop();info=json.loads((run/'report.json').read_text(encoding='utf-8')) if (run/'report.json').exists() else {}
   part['runs'].append({'run':str(run),'state':info.get('state'),'returncode':child.returncode,'training_seconds':info.get('training_seconds',0),'steps':info.get('optimizer_steps',len(info.get('steps',[])))})
   if child.returncode or info.get('state')!='trained':
    part['state']='failed'
    report.update(state='failed',reason=info.get('error','Trainer failed or memory protection stopped it'));save(report);return
   assert info['initial_adapter_hash']!=info['final_adapter_hash']
   resume=run/'adapter';part['actual_training_seconds']+=info['training_seconds'];part['optimizer_steps']+=info['optimizer_steps'];report['latest_adapter']=str(resume);save(report)
  part['state']='trained';save(report)
 report.update(state='trained_unvalidated',finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),note='Training is not proof of improved accuracy. Existing active adapter and GGUF were not changed. Evaluation and GGUF conversion/application remain separate.');save(report)
if __name__=='__main__':
 try:main()
 except Exception as e:
  current=json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
  current.update(state='failed',error=type(e).__name__+': '+str(e));save(current);raise
