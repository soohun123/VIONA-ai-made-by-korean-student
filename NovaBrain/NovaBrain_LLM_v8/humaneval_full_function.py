"""New HumanEval full-function protocol. One generation per task, no repairs/resume."""
import argparse
import datetime
import gzip
import hashlib
import json
import uuid
import urllib.request
from pathlib import Path

from coding_workflow import SYSTEM, chat, check_source, extract_source, resource_guard
from coding_policy import POLICY_VERSION

ROOT = Path(__file__).resolve().parent
DATA_HASH = 'b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, choices=range(1, 165), default=164)
    parser.add_argument('--max-tokens', type=int, default=2048, help='256..16384 output tokens; must fit server context')
    parser.add_argument('--evaluate', action='store_true')
    args = parser.parse_args()
    if not 256 <= args.max_tokens <= 16384:
        parser.error('--max-tokens must be 256..16384')
    dataset = ROOT / 'humaneval/HumanEval.jsonl.gz'
    if hashlib.sha256(dataset.read_bytes()).hexdigest() != DATA_HASH:
        raise SystemExit('Dataset checksum mismatch')
    with gzip.open(dataset, 'rt', encoding='utf-8') as handle:
        tasks = [json.loads(line) for line in handle]
    if len(tasks) != 164 or len({t['task_id'] for t in tasks}) != 164:
        raise SystemExit('Invalid task set')
    run = ROOT / 'humaneval/runs' / uuid.uuid4().hex
    run.mkdir(parents=True)
    manifest = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'dataset_sha256': DATA_HASH, 'protocol': 'full-function-v2',
                'coding_policy': POLICY_VERSION,
                'development_exposure': 'General coding guidance revised after static review of 63 failures in run 9766ce49947c42f585e3550bd589c7a8; no canonical solutions added to inference or training.',
                'system_prompt': SYSTEM, 'temperature': 0, 'top_p': 1, 'seed': 42,
                'max_tokens': args.max_tokens, 'requested_tasks': args.limit,
                'repairs': 0, 'sample_reuse': False,
                'runtime': 'CPython 3.11.4 WASI, 256 MiB, 10s, no network, read-only stdlib',
                'note': 'Changed protocol; does not replace historical body-only results.'}
    import model_catalog
    selected = model_catalog.choose('text', 'text-coding', 'coding', False)
    if not selected:
        raise SystemExit('Coding model profile unavailable')
    model_path = model_catalog.path_for(selected['path'])
    resource_guard()
    model_digest = hashlib.sha256()
    with model_path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            model_digest.update(block)
    manifest['model'] = selected
    manifest['model_sha256'] = model_digest.hexdigest()
    stat = model_path.stat()
    model_fingerprint = (stat.st_size, stat.st_mtime_ns)
    with urllib.request.urlopen('http://127.0.0.1:8000/status', timeout=5) as response:
        status = json.load(response)
    context = status.get('context', 0)
    if context - args.max_tokens - max(256, (context * 3 + 99) // 100) < 128:
        parser.error(f'Server context {context} cannot fit output budget {args.max_tokens}; increase context first')
    manifest['server_start'] = {key: status.get(key) for key in
                              ('context', 'threads', 'gpu_requested_layers', 'gpu_layers', 'placement')}
    # Snapshot relevant source/config hashes without copying user secrets.
    manifest['files_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in ('coding_policy.py', 'coding_workflow.py', 'humaneval_full_function.py',
                                           'sandbox_eval.py', 'validate_install.py', 'engine.py', 'worker.py')}
    for name in ('runtime-settings.json', 'humaneval/run-manifest.json'):
        if (ROOT / name).exists():
            manifest['files_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    results = []
    sandbox = None
    if args.evaluate:
        resource_guard()
        from sandbox_eval import Sandbox
        sandbox = Sandbox()
    try:
        for task in tasks[:args.limit]:
            resource_guard()
            stat = model_path.stat()
            if model_catalog.choose('text', 'text-coding', 'coding', False) != selected or (stat.st_size, stat.st_mtime_ns) != model_fingerprint:
                raise RuntimeError('Coding model changed during run; partial results retained')
            # Never send canonical_solution or hidden checks to the model.
            response = chat([{'role': 'system', 'content': SYSTEM},
                             {'role': 'user', 'content': 'Implement this entire function, retaining its signature:\n' + task['prompt']}],
                            args.max_tokens)
            sample = {'task_id': task['task_id'], 'raw_response': response['reply'], 'metrics': response['metrics'],
                      'selected_model': response['selected_model']}
            with (run / 'samples.jsonl').open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(sample, ensure_ascii=False) + '\n')
            try:
                source = extract_source(response['reply'])
                tests = task['test'] + '\ncheck(' + task['entry_point'] + ')\n' if args.evaluate else None
                checked = check_source(source, sandbox, tests, task['entry_point'])
            except ValueError as exc:
                checked = {'syntax_valid': False, 'tests_passed': False if args.evaluate else None, 'error': str(exc)}
            if args.evaluate and not checked['syntax_valid']:
                checked['tests_passed'] = False
            results.append({'task_id': task['task_id'], **checked})
            with (run / 'checks.jsonl').open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(results[-1], ensure_ascii=False) + '\n')
            print(task['task_id'], flush=True)
    except Exception as exc:
        manifest['interrupted_error'] = type(exc).__name__ + ': ' + str(exc)[:2000]
        raise
    finally:
        passed = sum(r.get('tests_passed') is True for r in results)
        report = {'completed': len(results), 'total': 164, 'evaluated': args.evaluate,
                  'passed': passed if args.evaluate else None,
                  'partial_pass_rate': passed / len(results) if args.evaluate and results else None,
                  'full_humaneval_pass_at_1': passed / 164 if args.evaluate and len(results) == 164 else None,
                  'protocol': 'full-function-v2', 'coding_policy': POLICY_VERSION,
                  'interrupted_error': manifest.get('interrupted_error')}
        (run / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(run)


if __name__ == '__main__':
    main()
