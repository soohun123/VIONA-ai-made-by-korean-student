"""Developer-only practice manager; persisted state survives a web-server restart."""
import json,os,re,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parent
STORE=ROOT/'data/coding-learning'
LOCK=threading.Lock()


def directory(identifier):
    if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('잘못된 학습 ID입니다.')
    p=STORE/'runs'/identifier
    if not p.is_dir():raise ValueError('학습 기록이 없습니다.')
    return p


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(20):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05)


def alive(data):
    try:
        p=psutil.Process(data['pid'])
        return (abs(p.create_time()-data['created'])<.1 and Path(p.cwd()).resolve()==ROOT
                and any(Path(arg).name=='coding_learning_runner.py' for arg in p.cmdline()))
    except (OSError,ValueError,KeyError,psutil.Error):return False


def current():
    candidates=[]
    for name in ('current.json','starting.json'):
        try:
            data=read(STORE/name);report=read(directory(data['id'])/'report.json')
            candidates.append({**report,'process_alive':alive(data)})
        except (OSError,ValueError,KeyError):pass
    if not candidates:
        rows=history()
        if rows:candidates=[{**rows[0],'process_alive':False}]
    if not candidates:return None
    report=max(candidates,key=lambda r:(r.get('started',0),r['process_alive']))
    if not report['process_alive'] and report['state'] in ('running','starting'):
        report={**report,'state':'interrupted','phase':'stopped','error':'학습 프로세스가 종료되었습니다. 저장된 풀이와 교재는 보존되어 있습니다.'}
    return report


def history():
    rows=[]
    for p in sorted((STORE/'runs').glob('*/report.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:15]:
        try:rows.append(json.loads(p.read_text(encoding='utf-8')))
        except (OSError,ValueError):pass
    return rows


def start(config):
    from text_training_runtime import active_training
    with LOCK:
        active=current()
        if active and active['process_alive']:raise ValueError('이미 코딩 학습이 실행 중입니다.')
        if active_training():raise ValueError('가중치 학습이 이미 실행 중입니다.')
        if not (STORE/'curriculum-v1.jsonl').is_file():raise ValueError('검증된 학습 문제가 준비되지 않았습니다.')
        return spawn(config)


def spawn(config,source=None):
    run=STORE/'runs'/uuid.uuid4().hex;run.mkdir(parents=True)
    write(run/'config.json',config)
    report={'id':run.name,'state':'starting','phase':'practice','started':time.time(),
            'completed':0,'total':50*len(config['parts']),'first_passed':0,'repaired_passed':0,
            'teacher_examples':0,'coaching_count':0,'parts':{},'error':None}
    if source:
        previous=read(source/'report.json')
        for filename in ('attempts.jsonl','checks.jsonl','teaching.jsonl','coaching.jsonl'):
            if (source/filename).is_file():shutil.copy2(source/filename,run/filename)
        for key in ('completed','total','first_passed','repaired_passed','teacher_examples','coaching_count','parts','curriculum_sha256','curriculum_note'):
            if key in previous:report[key]=previous[key]
        report.update(source_run=source.name,practice_reused=True,phase='waiting_for_weight_setup')
        report['practice_source_sha256']=previous.get('practice_source_sha256',previous.get('source_sha256',{}))
    write(run/'report.json',report)
    (run/'allow-weight-phase').write_text('enabled by authenticated developer request',encoding='utf-8')
    with (run/'console.log').open('w',encoding='utf-8') as out:
        p=subprocess.Popen([sys.executable,'-u',str(ROOT/'coding_learning_runner.py'),str(run)],cwd=ROOT,
           stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'},creationflags=subprocess.CREATE_NO_WINDOW)
    process={'id':run.name,'pid':p.pid,'created':psutil.Process(p.pid).create_time(),'cwd':str(ROOT)}
    write(run/'process.json',process)
    # Reserve immediately: the child may take seconds to import WASI/model helpers.
    write(STORE/'starting.json',process)
    return {'id':run.name,'state':'starting'}


def resume(identifier,seconds):
    from text_training_runtime import active_training
    with LOCK:
        active=current()
        if active and active['process_alive'] or active_training():raise ValueError('다른 학습이 실행 중입니다.')
        source=directory(identifier);report=read(source/'report.json')
        if not report.get('total') or report.get('completed')!=report['total']:raise ValueError('전체 풀이가 완료된 기록만 사용할 수 있습니다.')
        teaching=source/'teaching.jsonl'
        if not teaching.is_file() or len(teaching.read_text(encoding='utf-8').splitlines())!=report['total']:raise ValueError('완료한 풀이의 교재 수가 일치하지 않습니다.')
        config=read(source/'config.json');config.update(training_seconds=seconds,resume_practice=True)
        return spawn(config,source)


def cancel(identifier):
    (directory(identifier)/'cancel').write_text('cancel requested by developer',encoding='utf-8')
    return {'ok':True,'notice':'진행 중인 응답·검사가 끝나면 중지합니다. 가중치 학습 중이면 해당 학습 프로세스만 중지합니다.'}


def details(identifier):
    run=directory(identifier);report=json.loads((run/'report.json').read_text(encoding='utf-8'))
    coaching=run/'coaching.jsonl'
    report['recent_coaching']=[]
    if coaching.exists():
        for line in coaching.read_text(encoding='utf-8').splitlines()[-5:]:
            try:report['recent_coaching'].append(json.loads(line))
            except ValueError:pass  # A writer may still be appending the last line.
    active=current()
    if active and active['id']==identifier:report.update({k:active[k] for k in ('state','phase','error','process_alive') if k in active})
    else:report['process_alive']=False
    report['can_resume']=not report['process_alive'] and bool(report.get('total')) and report.get('completed')==report['total'] and (run/'teaching.jsonl').is_file()
    if report.get('training_run'):
        path=ROOT/'data/text-training/runs'/report['training_run']/'report.json'
        if path.is_file():
            training=json.loads(path.read_text(encoding='utf-8'))
            report['weight_result']={k:training.get(k) for k in ('state','optimizer_steps','training_seconds','examples','seen_ids','skipped_examples','initial_adapter_hash','final_adapter_hash','cpu_mode')}
    return report
