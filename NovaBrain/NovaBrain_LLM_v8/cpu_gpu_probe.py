"""Measure only this installation's process tree during two chat generations."""
import argparse
import json
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import psutil
from coding_workflow import chat, resource_guard

ROOT = Path(__file__).resolve().parent
PROMPT = ('Write complete Python implementations of binary_search, merge_intervals, '
          'is_balanced and unique_in_order, with required imports. '
          'Preserve inputs, support empty inputs, return code only.')


def status():
    with urllib.request.urlopen('http://127.0.0.1:8000/status', timeout=5) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; refusing to overwrite')
    root = psutil.Process(json.loads((ROOT / 'server.pid.json').read_text())['pid'])
    if Path(root.cwd()).resolve() != ROOT or 'server:app' not in root.cmdline():
        raise RuntimeError('Server identity mismatch')
    result = {'start': status(), 'samples': [], 'responses': [], 'prompt': PROMPT,
              'cpu_definition': 'Sum of server process-tree CPU time divided by wall time and 12/logical CPU count; machine percent'}
    done = threading.Event()

    def monitor():
        previous, prior_time, tick = {}, time.monotonic(), 0
        while not done.is_set():
            now = time.monotonic()
            current, rss, private = {}, 0, 0
            try:
                for proc in [root] + root.children(recursive=True):
                    try:
                        times = proc.cpu_times()
                        current[proc.pid] = times.user + times.system
                        info = proc.memory_info()
                        rss += info.rss
                        private += getattr(info, 'private', 0)
                    except psutil.Error:
                        pass
                percent = sum(max(0, value - previous[pid]) for pid, value in current.items()
                              if pid in previous) / max(now - prior_time, .001) / psutil.cpu_count() * 100
                record = {'time': time.time(), 'cpu_machine_percent': percent,
                          'tree_rss': rss, 'tree_private': private,
                          'system_cpu': psutil.cpu_percent(None),
                          'available_gib': psutil.virtual_memory().available / 2**30}
                if tick % 4 == 0:
                    gpu = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used',
                                          '--format=csv,noheader,nounits'], capture_output=True,
                                         text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                    record['gpu'] = gpu.stdout.strip()
                result['samples'].append(record)
                previous, prior_time = current, now
                tick += 1
            except Exception as exc:
                result.setdefault('monitor_errors', []).append(str(exc))
            done.wait(.5)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        for _ in range(2):
            resource_guard()
            result['responses'].append(chat([{'role': 'system', 'content': 'Return complete Python code only.'},
                                             {'role': 'user', 'content': PROMPT}], 384))
    finally:
        done.set()
        thread.join(timeout=5)
        result['end'] = status()
        values = [s['cpu_machine_percent'] for s in result['samples'][1:]]
        result['summary'] = {'mean_cpu_machine_percent': statistics.mean(values) if values else None,
                             'peak_cpu_machine_percent': max(values, default=None),
                             'speed': [r['metrics']['tokens_per_second'] for r in result['responses']]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
