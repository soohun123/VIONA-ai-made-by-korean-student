"""Recognize only this installation's live, PID-verified text trainer."""
import json
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent
LEASE = ROOT / 'data/text-training/active-job.json'


def active_training():
    try:
        job = json.loads(LEASE.read_text(encoding='utf-8'))
        process = psutil.Process(job['pid'])
        if (job.get('state') == 'running' and abs(process.create_time() - job['process_created']) < .1
                and Path(process.cwd()).resolve() == ROOT
                and any(Path(arg).name == 'train_qwen_lora.py' for arg in process.cmdline())):
            return {'id': job['id'], 'pid': process.pid}
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return None
