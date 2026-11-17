"""Read published, immutable local website assets; never read API credentials."""
import json,re
from pathlib import Path

def read_release(root):
    root=Path(root).resolve();pointer=root/'data/deployments/current.json'
    identifier=json.loads(pointer.read_text(encoding='utf-8'))['id']
    if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('배포 ID 형식 오류')
    release=json.loads((root/'data/deployments'/identifier/'manifest.json').read_text(encoding='utf-8'))
    models=[];adapters=[]
    def asset(m,field):
        source=(root/m[field]).resolve()
        if not source.is_relative_to(root) or not source.is_file():raise ValueError('웹 배포 파일 경로를 확인해 주세요.')
        checksum=release['hashes'].get(m['id']+':'+field,'')
        if not re.fullmatch('[a-f0-9]{64}',checksum):raise ValueError('배포 파일 해시가 없습니다.')
        return {'source':str(source),'relative':'website-assets/'+source.name,'sha256':checksum,'size':source.stat().st_size}
    for m in release['models']:
        if not m.get('enabled',True):continue
        row={**asset(m,'path'),'id':'web-'+m['id'],'kind':m['kind'],'name':'웹 · '+m['name'],'instructions':m.get('instructions','')}
        if m.get('adapter'):
            adapter={**asset(m,'adapter'),'id':row['id']+'-adapter','name':m['name']+' LoRA','base_sha256':row['sha256']}
            suffix=Path(adapter['source']).suffix
            if m['kind']=='text' and suffix=='.gguf':row['text_adapter']=adapter
            elif m['kind']=='image' and suffix=='.safetensors':adapters.append(adapter);row['adapter_id']=adapter['id']
            else:raise ValueError('EXE가 지원하는 LoRA 형식과 다릅니다.')
        models.append(row)
    if not models:raise ValueError('웹에서 먼저 모델을 배포해 주세요.')
    return {'id':identifier,'name':release['name'],'models':models,'adapters':adapters}
