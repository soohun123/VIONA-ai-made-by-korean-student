"""Local photo manifests and completed SD1.5 LoRA adapters."""
import json,re,uuid,os,shutil,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATASETS=ROOT/'data/training/datasets'
LORAS=ROOT/'models/loras'

def dataset_path(dataset_id):
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',dataset_id):raise ValueError('올바르지 않은 사진 모음 ID입니다.')
    path=DATASETS/dataset_id/'dataset.json'
    if not path.resolve().is_relative_to(DATASETS.resolve()) or not path.is_file():raise ValueError('사진 모음을 찾을 수 없습니다.')
    return path

def datasets():
    rows=[]
    for path in DATASETS.glob('*/dataset.json'):
        try:
            d=json.loads(path.read_text(encoding='utf-8'));rows.append({'id':d['id'],'name':d['name'],'count':len(d['records']),'source':d.get('source',''),'license':d.get('license','')})
        except (OSError,ValueError,KeyError):continue
    return rows

def create_dataset(image_ids,name,caption):
    from media_jobs import image_path
    dataset_id='photos-'+uuid.uuid4().hex;directory=DATASETS/dataset_id;directory.mkdir(parents=True)
    records=[]
    for index,image_id in enumerate(dict.fromkeys(image_ids)):
        source=image_path(image_id)
        records.append({'image':str(source.relative_to(ROOT)),'relative_to_root':True,'caption':caption,'split':'validation' if len(image_ids)>=10 and index%10==0 else 'train'})
    data={'id':dataset_id,'name':name,'source':'user-uploaded local photos','records':records}
    (directory/'dataset.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return {'id':dataset_id,'count':len(records)}

def adapters():
    LORAS.mkdir(parents=True,exist_ok=True);rows=[]
    for path in sorted(LORAS.glob('*.json'),key=lambda p:p.stat().st_mtime):
        if not re.fullmatch('[a-f0-9]{32}\.json',path.name):continue
        try:
            d=json.loads(path.read_text(encoding='utf-8'))
            if (LORAS/(d['adapter_id']+'.safetensors')).is_file():rows.append(d)
        except (OSError,ValueError,KeyError):continue
    return rows

def adapter_path(adapter_id):
    if not re.fullmatch('[a-f0-9]{32}',adapter_id):raise ValueError('올바르지 않은 LoRA ID입니다.')
    path=LORAS/(adapter_id+'.safetensors')
    if not path.is_file() or not (LORAS/(adapter_id+'.json')).is_file():raise ValueError('완료된 LoRA를 찾을 수 없습니다.')
    return path

def adapter_metadata(adapter_id):
    adapter_path(adapter_id)
    return json.loads((LORAS/(adapter_id+'.json')).read_text(encoding='utf-8'))

def collect_training_records(dataset_id,parent=None,replay=True):
    current=json.loads(dataset_path(dataset_id).read_text(encoding='utf-8'))
    history=list(dict.fromkeys((parent.get('dataset_ids') or [parent['dataset_id']]) if parent else []))
    history=list(dict.fromkeys([i for i in history if i!=dataset_id]+[dataset_id]))
    merged={};previous_splits={}
    from PIL import Image
    for identifier in history:
        manifest=dataset_path(identifier);data=json.loads(manifest.read_text(encoding='utf-8'))
        for record in data['records']:
            path=ROOT/record['image'] if record.get('relative_to_root') else manifest.parent/record['image']
            if not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Image outside workspace')
            with Image.open(path) as image:
                if image.width*image.height>16000000:raise ValueError('Training photo too large')
                digest=hashlib.sha256(str(image.size).encode()+image.convert('RGB').tobytes()).hexdigest()
            if identifier!=dataset_id:previous_splits.setdefault(digest,record.get('split','train'))
            if not replay and identifier!=dataset_id:continue
            previous=merged.get(digest)
            row={**record,'image':str(path.relative_to(ROOT)),'relative_to_root':True,'dataset_id':identifier}
            if digest in previous_splits:row['split']=previous_splits[digest]
            elif previous:row['split']=previous.get('split','train')
            merged[digest]=row
            if len(merged)>1000:raise ValueError('누적 사진은 한 번에 최대 1,000장입니다. 복습을 끄거나 사진 모음을 나누세요.')
    return {**current,'records':list(merged.values())},history

def _replace(source,target):
    for attempt in range(20):
        try:os.replace(source,target);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05)

def rename(kind,item_id,name):
    name=name.strip()
    if not name or len(name)>80:raise ValueError('이름은 공백을 제외하고 1~80자로 입력해 주세요.')
    if kind=='dataset':path=dataset_path(item_id)
    elif kind=='adapter':adapter_path(item_id);path=LORAS/(item_id+'.json')
    else:raise ValueError('지원하지 않는 이름 변경 대상입니다.')
    data=json.loads(path.read_text(encoding='utf-8'))
    backup=ROOT/'data/training/metadata-backups';backup.mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,backup/(item_id+'-'+uuid.uuid4().hex+'.json'))
    data['name']=name;temporary=path.with_suffix('.rename.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');_replace(temporary,path)
    return {'id':item_id,'name':name}

def publish_adapter(job_id,parent_id,keep_previous,result,native_file,training_file):
    """Metadata-last commit. Replacing a visible version always retains a rollback backup."""
    if not re.fullmatch('[a-f0-9]{32}',job_id):raise ValueError('Invalid job ID')
    target=parent_id if parent_id and not keep_previous else job_id
    if parent_id:adapter_path(parent_id)
    files=[(Path(native_file),LORAS/(target+'.safetensors')),(Path(training_file),LORAS/(target+'.training.safetensors'))]
    metadata=LORAS/(target+'.json');temporary=LORAS/(job_id+'.publish.tmp')
    result['adapter_id']=target;result['version_id']=job_id
    backup=None;old_paths=[]
    for source,destination in files:
        if not source.resolve().is_relative_to(LORAS.resolve()):raise ValueError('Staging file outside adapter directory')
    if target==parent_id:
        backup=ROOT.parent/'backups/training-replaced'/parent_id/job_id
        if not backup.resolve().is_relative_to((ROOT.parent/'backups').resolve()):raise ValueError('Backup outside workspace')
        backup.mkdir(parents=True,exist_ok=False)
        for path in [d for _,d in files]+[metadata]:
            if path.exists():shutil.copy2(path,backup/path.name);old_paths.append(path)
        result['replaced_version_backup']=str(backup.relative_to(ROOT.parent))
    elif any(p.exists() for p in [d for _,d in files]+[metadata]):raise ValueError('New adapter ID already exists')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    committed=[]
    try:
        for source,destination in files+[(temporary,metadata)]:_replace(source,destination);committed.append(destination)
    except Exception:
        for path in committed:
            if path in old_paths:shutil.copy2(backup/path.name,path)
            else:path.unlink(missing_ok=True)
        raise
    return result
