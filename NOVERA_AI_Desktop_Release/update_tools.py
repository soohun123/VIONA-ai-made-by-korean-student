"""Build-time signed local update publisher. Signing key never enters the app."""
import argparse,base64,hashlib,json,os,shutil,subprocess,zipfile,time
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding
ROOT=Path(__file__).resolve().parent
FEED=Path('D:/수혀니당/Documents/NOVERA_AI_Updates')
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def atomic(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8');
 for attempt in range(20):
  try:os.replace(temp,path);break
  except PermissionError:
   if attempt==19:raise
   time.sleep(.1)
def key():return serialization.load_pem_private_key((FEED/'.private/signing.pem').read_bytes(),password=None)
def initialize():
 private=FEED/'.private';private.mkdir(parents=True,exist_ok=True);p=private/'signing.pem'
 if not p.exists():
  if (FEED/'.indices').exists() and any((FEED/'.indices').glob('*.json')):raise ValueError('Signing key missing. Restore it; do not silently rotate the trusted update key.')
  value=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  with p.open('xb') as f:f.write(value.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
 value=key();n=value.public_key().public_numbers()
 def enc(x):return base64.b64encode(x.to_bytes((x.bit_length()+7)//8,'big')).decode()
 xml='<RSAKeyValue><Modulus>'+enc(n.n)+'</Modulus><Exponent>'+enc(n.e)+'</Exponent></RSAKeyValue>'
 atomic(ROOT/'assets/update-channel.json',{'manifest':str(FEED/'channel.json'),'enabled':True})
 source=(ROOT/'updater/Updater.cs').read_text(encoding='utf-8').replace('__PUBLIC_KEY_XML_BASE64__',base64.b64encode(xml.encode()).decode())
 folder=ROOT/'build/updater';folder.mkdir(parents=True,exist_ok=True);(folder/'Updater.generated.cs').write_text(source,encoding='utf-8')
 subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe','/nologo','/target:winexe','/platform:x64','/r:System.Web.Extensions.dll','/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll','/out:'+str(folder/'NOVERA_Update.exe'),str(folder/'Updater.generated.cs')],check=True)
 return folder/'NOVERA_Update.exe'
def allowed(name):
 return (name in ('NOVERA_AI_Desktop.exe','NOVERA_Update.exe','app-version.json') or name.startswith('_internal/')) and Path(name).suffix.lower() not in ('.gguf','.safetensors','.pt','.pth','.bin') and not any(x in ['.secrets','model-pack','accounts','exports'] for x in name.lower().split('/'))
def envelope(manifest):
 body=json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
 return {'payload':base64.b64encode(body).decode(),'signature':base64.b64encode(key().sign(body,padding.PKCS1v15(),hashes.SHA256())).decode()}
def publish(stage):
 stage=Path(stage);version=json.loads((stage/'app-version.json').read_text(encoding='utf-8'))['version'];indices=FEED/'.indices';indices.mkdir(exist_ok=True)
 index={}
 for p in stage.rglob('*'):
  if p.is_file():
   name=p.relative_to(stage).as_posix()
   if allowed(name):index[name]={'sha256':digest(p),'size':p.stat().st_size}
 own=indices/(version+'.json')
 if own.exists():
  if json.loads(own.read_text(encoding='utf-8'))!=index:raise ValueError('Version already published with different bytes. Increase VERSION.txt.')
  print('Already published',version);return
 history={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in indices.glob('*.json')}
 def ver(s):return tuple(map(int,s.split('.')))
 if history and ver(version)<=max(map(ver,history)):raise ValueError('Refusing version downgrade/reuse')
 changed=[]
 for name,info in index.items():
  if any(old.get(name,{}).get('sha256')!=info['sha256'] for old in history.values()):
   changed.append({'path':name,**info,'before':{v:old.get(name,{}).get('sha256') for v,old in history.items()}})
 if history and not any(x['path']=='app-version.json' for x in changed):raise ValueError('Version file must change')
 if sum(x['size'] for x in changed)>2147483648:raise ValueError('Delta exceeds the updater size ceiling; use a full bootstrap installer')
 package='NOVERA-update-'+version+'.zip';target=FEED/package
 if target.exists():raise ValueError('Immutable update package already exists')
 temp=FEED/(package+'.part')
 with zipfile.ZipFile(temp,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
  for row in changed:z.write(stage/row['path'],row['path'])
 os.replace(temp,target)
 manifest={'schema':1,'app_id':'NOVERA_AI_Desktop','version':version,'supported_versions':sorted(history,key=ver),'files':changed,'package':package,'sha256':digest(target)}
 atomic(own,index);atomic(FEED/'channel.json',envelope(manifest));atomic(FEED/('release-'+version+'.json'),manifest)
 print('Published',version,'files',len(changed),'package bytes',target.stat().st_size)
def prepare_stage(stage):
 stage=Path(stage);version=(ROOT/'VERSION.txt').read_text().strip();atomic(stage/'app-version.json',{'app_id':'NOVERA_AI_Desktop','version':version})
 shutil.copy2(ROOT/'build/updater/NOVERA_Update.exe',stage/'NOVERA_Update.exe')
def next_version():
 path=ROOT/'VERSION.txt';v=path.read_text().strip()
 if (FEED/'.indices'/(v+'.json')).exists():
  parts=list(map(int,v.split('.')));parts[-1]+=1;v='.'.join(map(str,parts));path.write_text(v+'\n',encoding='utf-8')
 print('Build version',v)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['init','stage','publish','next-version']);p.add_argument('--stage',default='dist/NOVERA_AI_Desktop');a=p.parse_args()
 if a.action=='init':initialize()
 elif a.action=='stage':prepare_stage(a.stage)
 elif a.action=='next-version':next_version()
 else:publish(a.stage)
