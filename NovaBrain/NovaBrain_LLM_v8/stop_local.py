"""Stop only this installation's recorded server and its children."""
import json
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
record=json.loads((ROOT/'server.pid.json').read_text(encoding='utf-8'))
try:proc=psutil.Process(record['pid'])
except psutil.NoSuchProcess:raise SystemExit('Server already stopped')
cmd=' '.join(proc.cmdline()).lower()
if 'uvicorn' not in cmd or 'server:app' not in cmd or Path(proc.cwd()).resolve()!=ROOT:
    raise SystemExit('Recorded PID does not match this server; nothing stopped')
children=proc.children(recursive=True)
for child in reversed(children):
    try:child.terminate()
    except psutil.NoSuchProcess:pass
proc.terminate()
_,alive=psutil.wait_procs(children+[proc],timeout=5)
for child in alive:
    try:child.kill()
    except psutil.NoSuchProcess:pass
print('NovaBrain server stopped')
