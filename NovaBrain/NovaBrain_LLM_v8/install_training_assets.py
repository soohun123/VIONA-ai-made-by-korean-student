"""Pinned local SD1.5 training and CLIP screening assets; no image uploads."""
import concurrent.futures,hashlib,json,urllib.request
from pathlib import Path
from install_media_assets import download
ROOT=Path(__file__).resolve().parent
repos=[('stable-diffusion-v1-5/stable-diffusion-v1-5','451f4fe16113bff5a5d2269ed5ad43b0592e9a14','models/training/sd15'),('openai/clip-vit-base-patch32','3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268','models/moderation/clip')]
assets=[]
for repo,revision,folder in repos:
    metadata=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+repo+'/revision/'+revision+'?blobs=true',timeout=30))
    for f in metadata['siblings']:
        name=f['rfilename']
        if repo.startswith('stable'):
            allowed=name.split('/')[0] in ('unet','vae','text_encoder','tokenizer','scheduler') and (name.endswith(('.json','.txt')) or name.endswith('.fp16.safetensors'))
        else:allowed=name.endswith(('.json','.txt')) or name=='pytorch_model.bin'
        if not allowed:continue
        url='https://huggingface.co/'+repo+'/resolve/'+revision+'/'+name
        lfs=f.get('lfs',{})
        if lfs:sha=lfs['sha256'];size=lfs['size']
        else:
            data=urllib.request.urlopen(url,timeout=30).read();sha=hashlib.sha256(data).hexdigest();size=len(data)
        assets.append({'name':name,'repo':repo,'revision':revision,'path':str(ROOT/folder/name),'url':url,'sha256':sha,'size':size})
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=[]
    for result in pool.map(download,assets):results.append(result);print('READY',result['name'],flush=True)
(ROOT/'training-assets-manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('ALL_TRAINING_ASSETS_READY',flush=True)
