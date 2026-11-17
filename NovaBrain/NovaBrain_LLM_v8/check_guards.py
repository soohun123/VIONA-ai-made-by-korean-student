"""Boundary checks with synthetic measurements, never real RAM exhaustion."""
import json,os,subprocess,sys
from types import SimpleNamespace
from unittest.mock import patch
import server
results={}
def vm(used):return SimpleNamespace(total=int(15.87*2**30),used=int(used*2**30),available=int((15.87-used)*2**30))
with patch.object(server,'rss_gb',return_value=1.9):
    for used in (12.9,13,13.5,13.9):
        server.samples.clear()
        warnings=server.warning_count
        with patch.object(server.psutil,'virtual_memory',return_value=vm(used)):
            reason=server.guard()
        results[str(used)]={'stop_reason':reason,'warning_added':server.warning_count>warnings}
assert results['12.9']['stop_reason'] is None
assert results['13']['warning_added']
assert results['13.5']['stop_reason']
assert results['13.9']['stop_reason']
env=os.environ.copy();env['NOVABRAIN_CTX']='32769'
r=subprocess.run([sys.executable,'-c','import engine; engine.startup(); assert engine.llm is None; print(engine.load_error)'],env=env,capture_output=True,text=True)
assert r.returncode==0
results['context_above_32768_rejected_before_load']=r.stdout.strip()
print(json.dumps(results,ensure_ascii=True,indent=2))
from pathlib import Path
Path('guard-validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
