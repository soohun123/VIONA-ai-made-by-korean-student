"""Local teaching practice with immutable first attempts and separate repair records."""
import hashlib,json,os,subprocess,sys,time,urllib.error,urllib.request,uuid
from pathlib import Path
import psutil
from coding_workflow import chat,check_source,extract_source,repair_messages,resource_guard,SYSTEM
from coding_policy import failure_feedback
from sandbox_eval import Sandbox

ROOT=Path(__file__).resolve().parent
STORE=ROOT/'data/coding-learning'


def write(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(30):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==29:raise
            time.sleep(.05)


def main():
    directory=Path(sys.argv[1]).resolve()
    if not directory.is_relative_to(STORE.resolve()):raise ValueError('Run outside learning store')
    config=json.loads((directory/'config.json').read_text(encoding='utf-8'))
    initial=json.loads((directory/'report.json').read_text(encoding='utf-8')) if (directory/'report.json').exists() else {}
    if initial and initial.get('state')!='starting':raise RuntimeError('Existing run cannot be overwritten; start a new run')
    process=psutil.Process();write(STORE/'current.json',{'id':directory.name,'pid':os.getpid(),'created':process.create_time()})
    report={'id':directory.name,'state':'running','phase':'practice','completed':0,'total':200,
        'first_passed':0,'repaired_passed':0,'teacher_examples':0,'parts':{},'started':time.time(),
        'repairs':config['repairs'],'training_seconds':config['training_seconds'],'coaching_count':0,
        'curriculum_note':'4 parts; 10 authored families x 5 parameter variants per part. Teaching set, not an independent benchmark.',
        'source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('coding_curriculum.py','coding_learning_runner.py','coding_policy.py','coding_workflow.py')}}
    if config.get('resume_practice'):
        for key in ('completed','total','first_passed','repaired_passed','teacher_examples','coaching_count','parts','curriculum_sha256','curriculum_note','source_run','practice_source_sha256'):
            if key in initial:report[key]=initial[key]
        report['practice_reused']=True
    write(directory/'report.json',report)
    def control():
        if (directory/'cancel').exists():raise InterruptedError('User cancelled learning')
        while (directory/'pause').exists():
            report['phase']='paused';write(directory/'report.json',report)
            if (directory/'cancel').exists():raise InterruptedError('User cancelled learning')
            time.sleep(1)
    try:
        corpus=STORE/'curriculum-v1.jsonl'
        if not config.get('resume_practice'):report['curriculum_sha256']=hashlib.sha256(corpus.read_bytes()).hexdigest()
        rows=[json.loads(l) for l in corpus.read_text(encoding='utf-8').splitlines()]
        selected=[] if config.get('resume_practice') else [r for r in rows if r['part'] in config['parts']]
        if not config.get('resume_practice'):report['total']=len(selected)
        sandbox=Sandbox() if selected else None
        for task in selected:
            control();report.update(phase='practice',current_task=task['id']);write(directory/'report.json',report)
            messages=[{'role':'system','content':SYSTEM},{'role':'user','content':task['prompt']}]
            attempts=[];passed=False
            for attempt in range(config['repairs']+1):
                while True:
                    control()
                    try:resource_guard()
                    except RuntimeError:
                        report['phase']='waiting_for_memory';write(directory/'report.json',report);time.sleep(3);continue
                    try:response=chat(messages,384);break
                    except urllib.error.HTTPError as exc:
                        if exc.code not in (409,503):raise
                        report['phase']='waiting_for_other_work';write(directory/'report.json',report);time.sleep(3)
                    except RuntimeError as exc:
                        if not any(word in str(exc) for word in ('RAM','메모리')):raise
                        report.update(phase='waiting_for_memory',wait_reason=str(exc));write(directory/'report.json',report);time.sleep(3)
                record={'task_id':task['id'],'attempt':attempt,'raw_response':response['reply'],
                        'metrics':response['metrics'],'selected_model':response['selected_model']}
                # Preserve every raw attempt before validation or feedback.
                with (directory/'attempts.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
                try:
                    source=extract_source(response['reply']);checked=check_source(source,sandbox,task['checks'],task['entry_point'])
                except ValueError as exc:source=None;checked={'tests_passed':False,'error':str(exc)}
                record.update(checked);record['source']=source;attempts.append(record)
                if checked.get('tests_passed'):passed=True;break
                feedback=failure_feedback(checked)
                advice='요구한 반환 타입과 경계값, 원본 보존, 구간 끝점·정렬 순서를 다시 확인하세요. 검사 실패 위치를 기준으로 최소 수정하세요.'
                if attempt<config['repairs']:
                    report['coaching_count']+=1
                    with (directory/'coaching.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'task_id':task['id'],'attempt':attempt,'advice':advice,'observed_failure':feedback},ensure_ascii=False)+'\n')
                    messages=repair_messages(task['prompt'],response['reply'],feedback+'\n'+advice)
            first=bool(attempts[0].get('tests_passed'));report['first_passed']+=int(first);report['repaired_passed']+=int(passed)
            part=report['parts'].setdefault(task['part'],{'completed':0,'first_passed':0,'repaired_passed':0})
            part['completed']+=1;part['first_passed']+=int(first);part['repaired_passed']+=int(passed)
            answer=attempts[-1]['source'] if passed else task['reference_source']
            origin='model_first' if first else 'model_repaired' if passed else 'authored_teacher_reference'
            report['teacher_examples']+=int(not passed)
            teaching={'id':task['id'],'kind':'coding','origin':origin,'messages':[{'role':'user','content':task['prompt']},{'role':'assistant','content':'```python\n'+answer.strip()+'\n```'}]}
            with (directory/'teaching.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(teaching,ensure_ascii=False)+'\n')
            with (directory/'checks.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'task_id':task['id'],'part':task['part'],'first_passed':first,'repaired_passed':passed,'teaching_origin':origin,'attempts':attempts},ensure_ascii=False)+'\n')
            report['completed']+=1;write(directory/'report.json',report)
            print('PRACTICE',report['completed'],'/',report['total'],flush=True)
        report['phase']='waiting_for_weight_setup';write(directory/'report.json',report)
        while not (directory/'allow-weight-phase').exists():control();time.sleep(1)
        control()
        # A standalone, bounded trainer is started only after practice and API idle checks.
        while True:
            control()
            with urllib.request.urlopen('http://127.0.0.1:8000/api/media',timeout=10) as r:media=json.load(r)
            if not media['active_job']:break
            report['phase']='waiting_for_other_work';write(directory/'report.json',report);time.sleep(3)
        while True:
            control()
            try:
                with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/admin/restart',data=b'',method='POST'),timeout=10) as r:json.load(r)
                break
            except urllib.error.HTTPError as exc:
                if exc.code!=409:raise
                report['phase']='waiting_for_other_work';write(directory/'report.json',report);time.sleep(3)
        while psutil.virtual_memory().available<6*2**30:
            control();report.update(phase='waiting_for_memory',available_gib=round(psutil.virtual_memory().available/2**30,2))
            write(directory/'report.json',report);time.sleep(3)
        report['phase']='weight_training';write(directory/'report.json',report)
        args=[str(ROOT/'.training-venv/Scripts/python.exe'),str(ROOT/'train_qwen_lora.py'),'--seconds',str(config['training_seconds']),
              '--corpus',str(directory/'teaching.jsonl'),'--fast-cpu','--once']
        active=ROOT/'data/text-training/active-adapter.json'
        if active.exists():
            previous=json.loads(active.read_text(encoding='utf-8'));adapter=ROOT/previous['path']
            if (adapter.parent/'adapter').is_dir():args+=['--resume',str(adapter.parent/'adapter')]
        with (directory/'weight-training.log').open('w',encoding='utf-8') as log:
            child=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'},creationflags=subprocess.CREATE_NO_WINDOW)
            report['trainer_pid']=child.pid;write(directory/'report.json',report)
            while child.poll() is None:
                try:
                    lease=json.loads((ROOT/'data/text-training/active-job.json').read_text())
                    if lease.get('state')=='running' and lease.get('process_created',0)>=report['started']:
                        report['training_run']=lease['id'];write(directory/'report.json',report)
                except (OSError,ValueError):pass
                if (directory/'cancel').exists():
                    for p in psutil.Process(child.pid).children(recursive=True):
                        try:
                            if any(Path(a).name=='train_qwen_lora.py' for a in p.cmdline()) and Path(p.cwd()).resolve()==ROOT:p.terminate()
                        except psutil.Error:pass
                    child.terminate();raise InterruptedError('User cancelled weight training')
                time.sleep(2)
        if child.returncode:
            tail=(directory/'weight-training.log').read_text(encoding='utf-8',errors='replace')[-1800:]
            report['training_diagnostic']=tail
            raise RuntimeError('가중치 학습 중 오류가 발생했습니다. 오류 상세와 학습 기록을 확인하세요.')
        lease=json.loads((ROOT/'data/text-training/active-job.json').read_text());report['training_run']=lease['id']
        report['phase']='trained_pending_review';report['state']='done';report['finished']=time.time()
    except InterruptedError as exc:report.update(state='cancelled',phase='stopped',error=str(exc))
    except Exception as exc:report.update(state='error',phase='stopped',error=type(exc).__name__+': '+str(exc));raise
    finally:write(directory/'report.json',report)


if __name__=='__main__':main()
