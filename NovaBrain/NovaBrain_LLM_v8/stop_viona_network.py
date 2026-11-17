"""Stop only this installation's supervisor, gateway and cloudflared."""
import json
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
file=ROOT/'.network-run/supervisor.pid.json'
if not file.exists():raise SystemExit('Network supervisor is not running')
record=json.loads(file.read_text(encoding='utf-8'))
try:p=psutil.Process(record['pid'])
except psutil.NoSuchProcess:raise SystemExit('Network supervisor already stopped')
if str(ROOT/'autostart_viona.py').lower() not in ' '.join(p.cmdline()).lower():raise SystemExit('PID ownership mismatch; nothing stopped')
children=p.children(recursive=True)
p.terminate()
for child in reversed(children):
    try:child.terminate()
    except psutil.Error:pass
_,alive=psutil.wait_procs(children+[p],timeout=5)
for process in alive:
    try:process.kill()
    except psutil.Error:pass
print('VIONA HTTPS supervisor stopped. Local AI server remains running.')
