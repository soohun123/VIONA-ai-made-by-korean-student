"""Per-user login supervisor: local server, authenticated gateway, Quick Tunnel."""
import argparse,json,logging,msvcrt,os,re,socket,subprocess,sys,time,webbrowser
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'.network-run';RUN.mkdir(exist_ok=True)
CONFIG=ROOT/'network-settings.json'
logging.basicConfig(filename=str(RUN/'supervisor.log'),encoding='utf-8',level=logging.INFO,format='%(asctime)s %(message)s')

def save_settings(url):
    settings={'public_url':url,'cors_origins':[url] if url else [],'mode':'quick','brand':'VIONA'}
    temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps(settings,indent=2),encoding='utf-8');os.replace(temp,CONFIG)
    (ROOT.parent/'VIONA_HTTPS_URL.txt').write_text((url or 'HTTPS 연결 준비 중')+'\n',encoding='utf-8')
    if url:(ROOT.parent/'VIONA_HTTPS.url').write_text('[InternetShortcut]\nURL='+url+'\n',encoding='utf-8')

def healthy():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/status',timeout=3) as r:return r.status==200
    except OSError:return False

def spawn(args,label):
    with (RUN/(label+'.log')).open('a',encoding='utf-8') as log:
        return subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=log,stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,env={**os.environ,'PYTHONUTF8':'1'})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--open-browser',action='store_true');args=parser.parse_args()
    lock=(RUN/'supervisor.lock').open('a+b')
    if lock.seek(0,2)==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    (RUN/'supervisor.pid.json').write_text(json.dumps({'pid':os.getpid(),'script':str(Path(__file__).resolve())}),encoding='utf-8')
    gateway=None;tunnel=None;opened=False;next_tunnel=0;next_server=0;url='';started=time.monotonic()
    logging.info('VIONA startup supervisor started')
    while True:
        try:
            now=time.monotonic()
            if now>=next_server:
                next_server=now+15
                if not healthy():
                    result=subprocess.run([sys.executable,str(ROOT/'launch_local.py')],cwd=ROOT,capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                    logging.info('Local server launch exit=%s',result.returncode)
            if gateway is None or gateway.poll() is not None:
                gateway=spawn([sys.executable,'-m','uvicorn','https_gateway:app','--host','127.0.0.1','--port','8001','--no-access-log'],'gateway')
            if (tunnel is None or tunnel.poll() is not None) and now>=next_tunnel:
                next_tunnel=now+30;url='';save_settings('')
                (RUN/'tunnel.log').write_text('',encoding='utf-8')
                tunnel=spawn([str(ROOT.parent/'tools/cloudflared.exe'),'tunnel','--url','http://127.0.0.1:8001','--no-autoupdate'],'tunnel')
            if tunnel is not None and tunnel.poll() is None and not url:
                log=(RUN/'tunnel.log').read_text(encoding='utf-8',errors='replace')
                match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',log)
                if match:
                    url=match.group(0);save_settings(url);logging.info('Public HTTPS address: %s',url)
            if args.open_browser and not opened and healthy():
                if url:
                    webbrowser.open(url);opened=True
                elif now-started>60:
                    webbrowser.open('http://127.0.0.1:8000/');opened=True
            time.sleep(3)
        except Exception:
            logging.exception('Supervisor retry');time.sleep(5)

if __name__=='__main__':main()
