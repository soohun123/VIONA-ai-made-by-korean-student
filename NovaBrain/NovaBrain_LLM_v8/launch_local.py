"""Launch only this installation, with a loopback-only listener."""
import json,os,socket,subprocess,sys
from pathlib import Path
from runtime_settings import read_settings,layers_for_mode
ROOT=Path(__file__).resolve().parent
env=os.environ.copy()
cpu_threads=str(read_settings()['cpu_threads'])
env.update({'NOVABRAIN_CTX':env.get('NOVABRAIN_CTX','8192'),'NOVABRAIN_THREADS':cpu_threads,
 'NOVABRAIN_GPU_LAYERS':str(layers_for_mode(read_settings()['gpu_mode'])),'NOVABRAIN_MIN_FREE_GB':'2','NOVABRAIN_WARN_USED_GB':'13',
 'NOVABRAIN_STOP_USED_GB':'13.5','NOVABRAIN_HARD_USED_GB':'14',
 'OMP_NUM_THREADS':cpu_threads,'OPENBLAS_NUM_THREADS':cpu_threads,'PYTHONUTF8':'1'})
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',8000))==0:
        raise SystemExit('Port 8000 is already in use. Check existing server; no process was stopped.')
with (ROOT/'server.stdout.log').open('a',encoding='utf-8') as out,(ROOT/'server.stderr.log').open('a',encoding='utf-8') as err:
    p=subprocess.Popen([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port','8000'],
        cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
(ROOT/'server.pid.json').write_text(json.dumps({'pid':p.pid,'python':sys.executable}),encoding='utf-8')
print('NovaBrain server PID',p.pid,'http://127.0.0.1:8000')
