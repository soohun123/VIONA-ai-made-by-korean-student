"""Local signed updates, applied before model/UI startup; no network listener."""
import json,os,subprocess,sys,time,uuid,shutil
from pathlib import Path

def current_version(app):
 try:return json.loads((Path(app)/'app-version.json').read_text(encoding='utf-8'))['version']
 except (OSError,ValueError,KeyError):return 'unknown'

def check(app,bundle,data):
 app,bundle,data=Path(app),Path(bundle),Path(data);result={'enabled':True,'current_version':current_version(app),'available':False}
 try:
  config=json.loads((bundle/'assets/update-channel.json').read_text(encoding='utf-8'))
  feed=Path(config['manifest'])
  if not config.get('enabled',True):return {**result,'enabled':False}
  if not feed.is_absolute() or str(feed).startswith('\\\\'):raise ValueError('Only the configured local update folder is supported')
  if not feed.exists():return {**result,'status':'업데이트 폴더에 연결할 수 없습니다.'}
  helper=app/'NOVERA_Update.exe';out=data/'updates'/('check-'+uuid.uuid4().hex+'.json');out.parent.mkdir(parents=True,exist_ok=True)
  proc=subprocess.run([str(helper),'--check',str(feed),str(app),str(out)],creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
  answer=json.loads(out.read_text(encoding='utf-8'))
  return {**result,**answer,'status':'새 버전이 준비되었습니다.' if answer.get('available') else '서명 확인 완료 · 최신 버전입니다.' if answer.get('ok') else '업데이트 서명/설정을 확인해 주세요.'}
 except Exception as e:return {**result,'ok':False,'status':'업데이트 확인 실패 · 기존 앱으로 실행합니다.','error':str(e)}

def at_start(app,bundle,data,smoke=False):
 import psutil
 for process in psutil.process_iter(['pid','exe']):
  if process.info['pid']!=os.getpid() and process.info['exe'] and os.path.normcase(process.info['exe'])==os.path.normcase(str(Path(app)/'NOVERA_AI_Desktop.exe')):return False
 result=check(app,bundle,data);data=Path(data);folder=data/'updates';folder.mkdir(parents=True,exist_ok=True)
 (folder/'last-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 if not result.get('available') or not result.get('ok'):return False
 failed=folder/'apply-result.json'
 if failed.exists():
  previous=json.loads(failed.read_text(encoding='utf-8'))
  # A failed update is never retried in an endless startup loop.
  if not previous.get('ok') and previous.get('version')==result.get('version'):
   return False
 config=json.loads((Path(bundle)/'assets/update-channel.json').read_text(encoding='utf-8'))
 helpers=folder/'helpers';helpers.mkdir(exist_ok=True)
 helper=helpers/('NOVERA_Update-'+uuid.uuid4().hex+'.exe');shutil.copy2(Path(app)/'NOVERA_Update.exe',helper)
 args=[str(helper),'--apply',config['manifest'],str(app),str(failed),str(os.getpid()),'--restart']
 if smoke:args.append('--smoke-restart')
 subprocess.Popen(args,creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 return True
