"""Download pinned local inference assets. Verify publisher SHA256 before use."""
import concurrent.futures,hashlib,json,os,time,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODELS=ROOT/'models/media';SETUP=ROOT.parent/'setup';RUNTIME=ROOT/'media-runtime'
ASSETS=[
 {'name':'vision.gguf','repo':'corono1/moondream2-2b-q4_k_m-gguf','revision':'04528bf81e7204e31b232110a3b9eb95ac79b3b7','file':'moondream2-text-model-q4_k_m.gguf','sha256':'77baaa54e41cbfc24e305ee15f58ff2aca198517f658368f1be072d07b51f99d','size':919494048},
 {'name':'vision-mmproj.gguf','repo':'ggml-org/moondream2-20250414-GGUF','revision':'97d0efa4667189aea70998d0b1ee36a7a3214fcb','file':'moondream2-mmproj-f16-20250414.gguf','sha256':'4cc1cb3660d87ff56432ebeb7884ad35d67c48c7b9f6b2856f305e39c38eed8f','size':909777984},
 {'name':'sd15-q4.gguf','repo':'gpustack/stable-diffusion-v1-5-GGUF','revision':'dcac270609fffc0ce7c7d41a3c0e752721859f7c','file':'stable-diffusion-v1-5-Q4_0.gguf','sha256':'c2f6e92f9d08d69cc673a1003528ac8199274b3c0eaec88d5fbefe5af67bd42b','size':1747190784},
]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def download(asset):
    path=Path(asset['path']);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if sha(path)==asset['sha256']:return {**asset,'verified':True,'reused':True}
        raise RuntimeError('Existing asset differs; not overwritten: '+str(path))
    part=path.with_suffix(path.suffix+'.download-part')
    for attempt in range(3):
        try:
            start=part.stat().st_size if part.exists() else 0
            headers={'User-Agent':'NovaBrain-local-model-installer'}
            if start:headers['Range']=f'bytes={start}-'
            with urllib.request.urlopen(urllib.request.Request(asset['url'],headers=headers),timeout=60) as response:
                append=start>0 and response.status==206
                with part.open('ab' if append else 'wb') as out:
                    while True:
                        block=response.read(1024*1024)
                        if not block:break
                        out.write(block)
            if part.stat().st_size!=asset['size'] or sha(part)!=asset['sha256']:raise RuntimeError('Asset size/hash mismatch: '+asset['name'])
            os.replace(part,path);print('VERIFIED',asset['name'],path.stat().st_size,flush=True)
            return {**asset,'verified':True,'reused':False}
        except Exception as e:
            print('DOWNLOAD_RETRY',asset['name'],attempt+1,type(e).__name__,str(e)[:160],flush=True)
            if attempt==2:raise
            time.sleep(2)
def main():
    MODELS.mkdir(parents=True,exist_ok=True);SETUP.mkdir(exist_ok=True);RUNTIME.mkdir(exist_ok=True)
    assets=[]
    for item in ASSETS:
        assets.append({**item,'path':str(MODELS/item['name']),'url':f'https://huggingface.co/{item["repo"]}/resolve/{item["revision"]}/{item["file"]}'})
    request=urllib.request.Request('https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/tags/master-1098-b521db4',headers={'User-Agent':'NovaBrain-local-model-installer'})
    with urllib.request.urlopen(request,timeout=20) as response:release=json.load(response)
    for suffix in ('bin-win-cuda12-x64.zip','bin-win-cpu-x64.zip'):
        item=next(a for a in release['assets'] if a['name'].endswith(suffix))
        digest=item.get('digest','')
        if not digest.startswith('sha256:'):raise RuntimeError('Missing publisher release digest')
        assets.append({'name':item['name'],'url':item['browser_download_url'],'path':str(SETUP/item['name']),'sha256':digest[7:],'size':item['size'],'release':release['tag_name']})
    report=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(download,a) for a in assets]
        for future in concurrent.futures.as_completed(futures):
            result=future.result();report.append(result)
            (ROOT/'media-assets-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            if result['name'].endswith('.zip'):
                folder=RUNTIME/('cuda' if 'cuda12' in result['name'] else 'cpu');folder.mkdir(exist_ok=True)
                with zipfile.ZipFile(result['path']) as archive:
                    for member in archive.infolist():
                        dest=(folder/member.filename).resolve()
                        if not dest.is_relative_to(folder.resolve()):raise RuntimeError('Unsafe archive path')
                        if dest.exists():continue
                        archive.extract(member,folder)
    print('ALL_MEDIA_ASSETS_READY',flush=True)
if __name__=='__main__':main()
