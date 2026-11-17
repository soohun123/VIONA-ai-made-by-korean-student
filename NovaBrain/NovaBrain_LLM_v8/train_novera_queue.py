"""Run imported photo batches serially via the existing protected local trainer."""
import argparse
import datetime
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil
from training_store import adapter_metadata

URL = 'http://127.0.0.1:8000'


def api(path, payload=None):
    headers = {}
    if payload is not None:
        with urllib.request.urlopen(URL + '/api/capabilities', timeout=10) as response:
            headers['x-novabrain-token'] = json.load(response)['tool_token']
        headers['Content-Type'] = 'application/json'
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(URL + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-manifest', required=True, type=Path)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--name', default='VIONA image1.5')
    args = parser.parse_args()
    data = json.loads(args.import_manifest.read_text(encoding='utf-8'))
    output = args.import_manifest.parent / 'queue.json'
    if output.exists():
        parser.error('Queue already exists; refusing to repeat completed training')
    parent = adapter_metadata(args.parent)
    queue = {'state': 'starting', 'name': args.name, 'parent_adapter_id': args.parent,
             'parent_initial_weight_hash': parent['final_weight_hash'],
             'keep_previous': False, 'replay_previous': False, 'resolution': 128,
             'cpu_threads': 3, 'import_manifest': str(args.import_manifest.resolve()),
             'import_sha256': hashlib.sha256(args.import_manifest.read_bytes()).hexdigest(),
             'planned_batches': len(data['batches']), 'planned_steps': sum(b['steps'] for b in data['batches']),
             'completed_batches': [], 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def save():
        # A queue reader may hold the file briefly on Windows.
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(20):
            try:
                temporary.replace(output)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.1)

    save()
    try:
        for index, batch in enumerate(data['batches']):
            expected_hash = queue['completed_batches'][-1]['result']['final_weight_hash'] if queue['completed_batches'] else queue['parent_initial_weight_hash']
            if adapter_metadata(args.parent)['final_weight_hash'] != expected_hash:
                raise RuntimeError('Parent changed outside this queue; stopping to preserve user work')
            if api('/api/media').get('active_job'):
                raise RuntimeError('Another media job is active; not interrupted')
            queue.update(state='waiting_for_ram', batch=index + 1)
            save()
            deadline = time.monotonic() + 600
            while psutil.virtual_memory().available < 6 * 2**30:
                if time.monotonic() > deadline:
                    raise RuntimeError('Training still needs 6 GiB free RAM; queue stopped')
                time.sleep(10)
            payload = {'dataset_id': batch['dataset_id'], 'name': args.name, 'steps': batch['steps'],
                       'resolution': 128, 'resume_adapter_id': args.parent,
                       'replay_previous': False, 'keep_previous': False}
            job = api('/api/training/jobs', payload)
            queue.update(state='running', active_job_id=job['id'], active_job=job)
            save()
            print('BATCH', index + 1, '/', len(data['batches']), 'JOB', job['id'], flush=True)
            while job['state'] in ('queued', 'running'):
                time.sleep(10)
                job = api('/api/media/jobs/' + job['id'])
                queue['active_job'] = job
                save()
            if job['state'] != 'done':
                raise RuntimeError('Training ' + job['state'] + ': ' + str(job.get('error')))
            result = job['result']
            if result['adapter_id'] != args.parent or result.get('keep_previous') is not False:
                raise RuntimeError('Unexpected adapter replacement settings')
            if result['seen_train_images'] < result['train_images']:
                raise RuntimeError('Batch did not see all admitted training images')
            queue['completed_batches'].append({'dataset_id': batch['dataset_id'], 'job_id': job['id'], 'result': result})
            queue['active_job_id'] = None
            save()
        queue['state'] = 'done'
        queue['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    except BaseException as exc:
        queue['state'] = 'stopped'
        queue['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        save()
        print(output, flush=True)


if __name__ == '__main__':
    main()
