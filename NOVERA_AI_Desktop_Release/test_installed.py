"""Run the installed EXE and measure its own process tree, not unrelated apps."""
import argparse,json,os,subprocess,time
from pathlib import Path
import psutil

def main():
 p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--gpu',action='store_true');p.add_argument('--images',action='store_true');a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=True);env={**os.environ,'NOVERA_DATA_DIR':str(a.output.resolve())}
 args=[str(a.exe.resolve()),'--self-test']+(['--test-image'] if a.images else [])+(['--test-gpu'] if a.gpu else [])
 app=subprocess.Popen(args,env=env,creationflags=subprocess.CREATE_NO_WINDOW);samples=[];deadline=time.monotonic()+900
 while app.poll() is None:
  if time.monotonic()>deadline:
   for child in psutil.Process(app.pid).children(recursive=True):child.terminate()
   app.terminate();raise TimeoutError('Installed test exceeded deadline')
  try:
   tree=[psutil.Process(app.pid)]+psutil.Process(app.pid).children(recursive=True)
   rss=sum(x.memory_info().rss for x in tree);cpu=sum(sum(x.cpu_times()[:2]) for x in tree)
   sample={'time':time.time(),'pids':sorted(x.pid for x in tree),'rss_gib':rss/2**30,'cpu_seconds_live_tree':cpu,'system_used_gib':psutil.virtual_memory().used/2**30}
   g=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
   try:r=g.stdout.strip().split(',');sample.update(vram_used_mib=int(r[0]),gpu_utilization=int(r[1]))
   except Exception:pass
   samples.append(sample)
  except psutil.Error:pass
  time.sleep(1)
 (a.output/'resource-samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
 print('exit',app.returncode,'samples',len(samples),flush=True)
 result=json.loads((a.output/'self-test.json').read_text(encoding='utf-8'));print('PASSED',result.get('passed'),flush=True)
 if not result.get('passed'):raise SystemExit(1)
if __name__=='__main__':main()
