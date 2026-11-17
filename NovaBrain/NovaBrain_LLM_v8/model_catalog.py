"""Developer drafts and immutable published model/UI/knowledge snapshots."""
import copy,hashlib,hmac,json,re,shutil,sqlite3,threading,time,uuid,contextlib
from pathlib import Path
from api_credentials import load_api_key
import domain_knowledge
ROOT=Path(__file__).resolve().parent
DRAFT=ROOT/'data/models-draft.json';RELEASES=ROOT/'data/deployments';LOCK=threading.RLock()
UI_FILES={'ui.html','ui.js','app.css','media-ui.js','models-ui.js','markdown-it.min.js','markdown-it.LICENSE'}
NAMES={'general':'일반','aviation':'항공','ai':'AI','computer':'컴퓨터','coding':'코딩','language':'문법·글쓰기'}
def seal():return hmac.new(load_api_key().encode(),b'viona-public-gateway-v1',hashlib.sha256).hexdigest()
def is_public(request):return bool(request) and hmac.compare_digest(request.headers.get('x-viona-public',''),seal())
def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(20):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05)
def draft():
    with LOCK:
        if DRAFT.is_file():data=json.loads(DRAFT.read_text(encoding='utf-8'))
        else:
            data={'models':[{'id':'text-'+d,'name':n+' · Qwen 공용 가중치','kind':'text','path':'model.gguf','domains':[d],'instructions':'','enabled':True,'publish':True,'specialty_trained':False} for d,n in NAMES.items()]+[{'id':'image-sd15','name':'Stable Diffusion 1.5','kind':'image','path':'models/media/sd15-q4.gguf','domains':[],'instructions':'','enabled':True,'publish':True,'specialty_trained':False}]}
            atomic(DRAFT,data)
        from training_store import adapters
        known={m['id'] for m in data['models']}
        for a in adapters():
            identifier='image-'+a['adapter_id']
            if identifier not in known:data['models'].append({'id':identifier,'name':a['name'],'kind':'image','path':'models/media/sd15-q4.gguf','adapter':'models/loras/'+a['adapter_id']+'.safetensors','domains':[],'instructions':'','enabled':True,'publish':False,'specialty_trained':True})
        return data
def release(identifier=None):
    if not identifier:
        pointer=RELEASES/'current.json'
        if not pointer.is_file():return None
        identifier=json.loads(pointer.read_text(encoding='utf-8'))['id']
    if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('올바르지 않은 배포 ID입니다.')
    path=RELEASES/identifier/'manifest.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
def path_for(value):
    path=(ROOT/value).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():raise ValueError('설치 폴더 안의 모델 파일을 선택해 주세요.')
    return path
def save_model(model):
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',model['id']):raise ValueError('모델 ID는 영문 소문자·숫자·하이픈으로 입력하세요.')
    file=path_for(model['path'])
    if file.suffix!='.gguf':raise ValueError('현재 실행기는 GGUF 파일을 사용합니다.')
    if model.get('adapter'):path_for(model['adapter'])
    with LOCK:
        data=draft();data['models']=[m for m in data['models'] if m['id']!=model['id']]+[model];atomic(DRAFT,data)
    return public_model(model)
def public_model(model):return {k:v for k,v in model.items() if k not in ('path','adapter','instructions')}
def models(public=False):
    data=release() if public else draft()
    return [m for m in (data or {}).get('models',[]) if m.get('enabled',True)]
def choose(kind,identifier,domain='general',public=False):
    rows=[m for m in models(public) if m['kind']==kind]
    if identifier and identifier!='auto':
        found=next((m for m in rows if m['id']==identifier),None)
        if not found:raise ValueError('선택한 모델이 없거나 배포되지 않았습니다. 새로고침해 주세요.')
        return found
    selected=next((m for m in rows if domain in m.get('domains',[])),None)
    return selected or (rows[0] if rows else None)
def publish(name):
    import content_filter
    with LOCK:
        selected=[copy.deepcopy(m) for m in draft()['models'] if m.get('publish') and m.get('enabled')]
        if not selected:raise ValueError('웹에 배포할 모델을 하나 이상 선택하세요.')
        identifier=uuid.uuid4().hex;directory=RELEASES/identifier;directory.mkdir(parents=True)
        assets=RELEASES/'assets';assets.mkdir(exist_ok=True)
        hashes={};frozen={}
        for model in selected:
            for field in ('path','adapter'):
                if not model.get(field):continue
                source=path_for(model[field])
                if source in frozen:
                    model[field],hashes[model['id']+':'+field]=frozen[source];continue
                h=hashlib.sha256()
                with source.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
                digest=h.hexdigest();target=assets/(digest+source.suffix)
                if not target.exists():
                    temporary=assets/(identifier+'-'+digest+'.tmp');shutil.copy2(source,temporary);temporary.replace(target)
                model[field]=str(target.relative_to(ROOT));hashes[model['id']+':'+field]=digest
                frozen[source]=(model[field],digest)
        ui=directory/'ui';ui.mkdir()
        for file in UI_FILES:shutil.copy2(ROOT/file,ui/file)
        domain_knowledge.snapshot(directory/'knowledge.sqlite')
        data={'id':identifier,'name':name,'created_at':time.time(),'models':selected,'hashes':hashes,'moderation':content_filter.settings(),'knowledge':domain_knowledge.summary(directory/'knowledge.sqlite')}
        atomic(directory/'manifest.json',data);atomic(RELEASES/'current.json',{'id':identifier})
        return {'id':identifier,'name':name,'models':len(selected),'requires_page_reload':True}
def publish_ui(name):
    """Publish only UI, retaining the exact currently published model/knowledge data."""
    with LOCK:
        previous=release()
        if not previous:raise ValueError('UI를 갱신할 기존 배포가 없습니다.')
        identifier=uuid.uuid4().hex;directory=RELEASES/identifier
        ui=directory/'ui';ui.mkdir(parents=True)
        for file in UI_FILES:shutil.copy2(ROOT/file,ui/file)
        source=RELEASES/previous['id']/'knowledge.sqlite'
        shutil.copy2(source,directory/'knowledge.sqlite')
        data=copy.deepcopy(previous)
        data.update({'id':identifier,'name':name,'created_at':time.time(),'ui_parent_release':previous['id']})
        atomic(directory/'manifest.json',data)
        if release()['id']!=previous['id']:
            raise RuntimeError('배포가 변경되었습니다. 최신 배포를 확인한 뒤 다시 시도하세요.')
        atomic(RELEASES/'current.json',{'id':identifier})
        return {'id':identifier,'name':name,'ui_parent_release':previous['id'],'models_unchanged':True,'requires_page_reload':True}

def rollback(identifier):
    if not release(identifier):raise ValueError('배포를 찾을 수 없습니다.')
    with LOCK:atomic(RELEASES/'current.json',{'id':identifier})
    return {'id':identifier}
def history():
    rows=[]
    for path in RELEASES.glob('*/manifest.json'):
        d=json.loads(path.read_text(encoding='utf-8'));rows.append({k:d[k] for k in ('id','name','created_at')})
    return sorted(rows,key=lambda r:r['created_at'],reverse=True)
def access(resource,identifier,grant=False):
    RELEASES.mkdir(parents=True,exist_ok=True)
    with contextlib.closing(sqlite3.connect(RELEASES/'web-access.sqlite',timeout=20)) as c:
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS owned(kind TEXT,id TEXT,PRIMARY KEY(kind,id))')
            if grant:c.execute('INSERT OR IGNORE INTO owned VALUES(?,?)',(resource,identifier));return True
            return bool(c.execute('SELECT 1 FROM owned WHERE kind=? AND id=?',(resource,identifier)).fetchone())
