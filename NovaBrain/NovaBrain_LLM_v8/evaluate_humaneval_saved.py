"""Evaluate saved first samples in WASI without generating or replacing them."""
import argparse
import gzip
import hashlib
import json
import uuid
from pathlib import Path

from coding_workflow import check_source, extract_source, resource_guard
from humaneval_full_function import DATA_HASH

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Existing full-function run ID')
    args = parser.parse_args()
    if not args.run.isalnum():
        parser.error('Invalid run ID')
    run = ROOT / 'humaneval/runs' / args.run
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('protocol') not in ('full-function-v1', 'full-function-v2'):
        parser.error('Only full-function protocol samples are supported')
    dataset = ROOT / 'humaneval/HumanEval.jsonl.gz'
    if hashlib.sha256(dataset.read_bytes()).hexdigest() != DATA_HASH:
        parser.error('Dataset checksum mismatch')
    with gzip.open(dataset, 'rt', encoding='utf-8') as handle:
        tasks = {t['task_id']: t for t in map(json.loads, handle)}
    sample_file = run / 'samples.jsonl'
    raw = sample_file.read_bytes()
    samples = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
    ids = [s['task_id'] for s in samples]
    if len(ids) != len(set(ids)) or not set(ids).issubset(tasks):
        parser.error('Duplicate or unknown task IDs; sample selection refused')
    output = run / 'evaluations' / uuid.uuid4().hex
    output.mkdir(parents=True)
    (output / 'manifest.json').write_text(json.dumps({
        'source_run': args.run, 'source_samples_sha256': hashlib.sha256(raw).hexdigest(),
        'source_manifest_sha256': hashlib.sha256((run / 'manifest.json').read_bytes()).hexdigest(),
        'dataset_sha256': DATA_HASH, 'source_protocol': manifest['protocol'],
        'max_tokens': manifest.get('max_tokens'), 'new_generation': False, 'repairs': 0,
        'runtime': 'CPython 3.11.4 WASI, 256 MiB, 10s, no network, read-only stdlib',
        'evaluator_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in ('evaluate_humaneval_saved.py', 'coding_workflow.py', 'sandbox_eval.py')}
    }, indent=2), encoding='utf-8')
    results, error = [], None
    try:
        resource_guard()
        from sandbox_eval import Sandbox
        sandbox = Sandbox()
        for sample in samples:
            resource_guard()
            task = tasks[sample['task_id']]
            try:
                source = extract_source(sample['raw_response'])
                checked = check_source(source, sandbox,
                    task['test'] + '\ncheck(' + task['entry_point'] + ')\n', task['entry_point'])
            except ValueError as exc:
                checked = {'syntax_valid': False, 'tests_passed': False, 'error': str(exc)}
            results.append({'task_id': task['task_id'], **checked})
            with (output / 'checks.jsonl').open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(results[-1], ensure_ascii=False) + '\n')
            print(task['task_id'], flush=True)
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        passed = sum(r.get('tests_passed') is True for r in results)
        report = {'completed': len(results), 'total': 164, 'evaluated': True,
                  'passed': passed, 'partial_pass_rate': passed / len(results) if results else None,
                  'full_humaneval_pass_at_1': passed / 164 if len(results) == 164 else None,
                  'source_run': args.run, 'protocol': manifest['protocol'],
                  'new_generation': False, 'repairs': 0, 'interrupted_error': error}
        (output / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(output, flush=True)


if __name__ == '__main__':
    main()
