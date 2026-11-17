"""Read-only original inspection and isolated distribution preparation."""
import argparse,hashlib,json,shutil,zipfile,struct,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT.parent/'NovaBrain/NovaBrain_LLM_v8'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--include-qwen',action='store_true');a=parser.parse_args()
 for name in ['src','assets','licenses','artifacts','backup']:(ROOT/name).mkdir(exist_ok=True)
 backup=ROOT/'backup/original-source.zip'
 if not backup.exists():
  with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
   for p in SOURCE.iterdir():
    if p.is_file() and p.suffix in ('.py','.js','.css','.html','.md') :z.write(p,p.name)
   for name in ['runtime-settings.json','data/models-draft.json','data/text-training/active-adapter.json']:
    if (SOURCE/name).exists():z.write(SOURCE/name,name)
   for p in (SOURCE/'models/loras').glob('*.json'):z.write(p,str(p.relative_to(SOURCE)))
 print('BACKUP',backup,flush=True)
 for name in ['gguf_metadata.py','generation_resources.py']:shutil.copy2(SOURCE/name,ROOT/'src'/name)
 shutil.copy2(SOURCE/'viona-logo-v3.svg',ROOT/'assets/logo.svg')
 inventory=[]
 for folder in [SOURCE/'models',SOURCE/'data/text-training/runs']:
  for p in folder.rglob('*'):
   if p.is_file() and p.suffix in ('.gguf','.safetensors','.bin','.pt','.pth','.onnx'):
    inventory.append({'path':str(p),'size':p.stat().st_size,'sha256':sha(p),'bundled':False})
 model=SOURCE/'model.gguf';h=sha(model);inventory.append({'path':str(model),'size':model.stat().st_size,'sha256':h,'bundled':a.include_qwen})
 active=json.loads((SOURCE/'data/text-training/active-adapter.json').read_text(encoding='utf-8'))
 text_adapter=SOURCE/active['path'];sd=SOURCE/'models/media/sd15-q4.gguf';sdhash=sha(sd)
 aid='221b4c7cde8a4bcb99899ebbfa2387ed';lora=SOURCE/'models/loras'/(aid+'.safetensors');meta=json.loads(lora.with_suffix('.json').read_text(encoding='utf-8'))
 with lora.open('rb') as f:
  length=struct.unpack('<Q',f.read(8))[0];header=json.loads(f.read(length))
 tensors={k:v for k,v in header.items() if k!='__metadata__'}
 assert tensors and all(k.startswith('lora_unet_') for k in tensors),'Unexpected LoRA format'
 assert any(320 in v['shape'] for v in tensors.values()),'SD1.5 channels missing'
 manifest={'models':[{'id':'qwen-viona','name':'VIONA · Qwen2.5-Coder 1.5B','kind':'text','source':str(model),'relative':'models/qwen/model.gguf','sha256':h,'size':model.stat().st_size,'license':'Apache-2.0','text_adapter':{'name':active['name'],'source':str(text_adapter),'relative':'adapters/text/adapter.gguf','sha256':sha(text_adapter),'base_sha256':active['base_sha256']}},{'id':'sd15-viona','name':'VIONA · Stable Diffusion 1.5','kind':'image','source':str(sd),'relative':'models/image/sd15-q4.gguf','sha256':sdhash,'size':sd.stat().st_size,'license':'CreativeML Open RAIL-M; local source used, not embedded'}], 'adapters':[{'id':'viona-image15','name':'VIONA image1.5 · v8 손 학습 통합','source':str(lora),'relative':'adapters/image/'+lora.name,'sha256':sha(lora),'base_sha256':sdhash,'format':'SD1.5 Kohya LoRA','license':'Private local import only; 11k Hands reasonable academic fair use; other training provenance requires review','metadata':{k:meta.get(k) for k in ['version','total_steps','dataset_ids','final_weight_hash']}}]}
 (ROOT/'assets/model-sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 (ROOT/'artifacts/model-inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
 if a.include_qwen:
  dst=ROOT/'model-pack/models/qwen';dst.mkdir(parents=True,exist_ok=True)
  if not (dst/'model.gguf').exists():shutil.copy2(model,dst/'model.gguf')
  assert sha(dst/'model.gguf')==h
  urllib.request.urlretrieve('https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/LICENSE',ROOT/'licenses/Qwen-LICENSE.txt')
 print('MODELS',len(inventory),'LoRA',len(tensors),'source read-only',flush=True)
if __name__=='__main__':main()
