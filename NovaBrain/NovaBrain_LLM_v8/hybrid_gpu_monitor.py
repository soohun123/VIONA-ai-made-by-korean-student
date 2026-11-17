import json,time
from pathlib import Path
from validate_install import get
ROOT=Path(__file__).resolve().parent
with (ROOT/'hybrid-gpu-samples.jsonl').open('w',encoding='utf-8') as out:
    while True:
        try:
            status=get('/status');gpu=get('/api/gpu')
            out.write(json.dumps({'time':time.time(),'gpu':gpu,'worker_pid':status['worker_pid'],'placement':status.get('placement'),'errors':status['errors'],'restarts':status['restarts']})+'\n');out.flush()
            soak=json.loads((ROOT/'hybrid-validation.json').read_text(encoding='utf-8'))
            if 'passed' in soak:break
        except Exception as e:
            out.write(json.dumps({'time':time.time(),'monitor_error':repr(e)})+'\n');out.flush()
        time.sleep(1)
