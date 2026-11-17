"""Small non-benchmark smoke set. Candidate code runs only in WASI."""
import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = [
 ('page_count', 'Write page_count(items, page_size), returning pages needed for a nonnegative integer items and positive page_size. Zero items needs zero pages. Return one complete Python code block.',
  'assert page_count(0,7)==0\nassert page_count(14,7)==2\nassert page_count(15,7)==3'),
 ('mask_token', "Write mask_token(token). Keep the final four characters and replace each preceding character with '*'. For length <=4 mask every character. Return one complete Python code block.",
  "assert mask_token('')==''\nassert mask_token('abc')=='***'\nassert mask_token('abcdef')=='**cdef'"),
 ('line_totals', "Write line_totals(rows), returning a list with count * unit for each row dictionary. Do not mutate rows. Return one complete Python code block.",
  "assert line_totals([])==[]\nx=[{'count':2,'unit':7},{'count':0,'unit':8}]\nassert line_totals(x)==[14,0]\nassert x[0]=={'count':2,'unit':7}"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter', default='off')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; not overwritten')
    from runtime_settings import read_settings, layers_for_mode
    os.environ.update(NOVABRAIN_CTX='4096', NOVABRAIN_THREADS=str(read_settings()['cpu_threads']),
                      NOVABRAIN_GPU_LAYERS=str(layers_for_mode(read_settings()['gpu_mode'])),
                      NOVABRAIN_TEXT_LORA=args.adapter)
    import engine
    from coding_workflow import check_source, extract_source, resource_guard
    from sandbox_eval import Sandbox
    engine.startup()
    if engine.llm is None:
        raise RuntimeError(engine.load_error)
    if args.adapter != 'off' and not engine.text_adapter:
        raise RuntimeError('Candidate adapter was not loaded')
    result = {'adapter': engine.text_adapter, 'placement': engine.placement, 'coding': [], 'dialogue': []}
    sandbox = Sandbox()

    def generate(messages):
        resource_guard()
        started = time.monotonic()
        output = engine.llm.create_chat_completion(messages=messages, max_tokens=256,
                    temperature=0, top_p=1, repeat_penalty=1, frequency_penalty=0, seed=42)
        return output['choices'][0]['message']['content'], time.monotonic() - started

    try:
        for name, prompt, tests in TASKS:
            answer, elapsed = generate([{'role': 'system', 'content': 'Write correct concise Python code.'},
                                        {'role': 'user', 'content': prompt}])
            try:
                checked = check_source(extract_source(answer), sandbox, tests, name)
            except ValueError as exc:
                checked = {'tests_passed': False, 'error': str(exc)}
            result['coding'].append({'id': name, 'answer': answer, 'elapsed': elapsed, **checked})
        messages = [{'role':'system','content':'한국어로 마지막 질문에 직접 답하세요.'},
                    {'role':'user','content':'표지 색은 파랑으로 할게.'},
                    {'role':'assistant','content':'표지 색은 파랑입니다.'},
                    {'role':'user','content':'아니, 초록으로 바꿔.'},
                    {'role':'assistant','content':'초록으로 변경했습니다.'},
                    {'role':'user','content':'지금 표지 색은? 색 이름만 답해.'}]
        answer, elapsed = generate(messages)
        result['dialogue'].append({'id': 'latest_color', 'answer': answer, 'elapsed': elapsed,
                                   'passed': '초록' in answer and '파랑' not in answer})
        result['coding_passed'] = sum(r.get('tests_passed') is True for r in result['coding'])
        result['dialogue_passed'] = sum(r['passed'] for r in result['dialogue'])
    finally:
        engine.llm.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: result.get(k) for k in ('coding_passed', 'dialogue_passed')}))


if __name__ == '__main__':
    main()
