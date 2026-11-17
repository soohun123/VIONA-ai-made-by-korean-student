"""Small independently authored teaching set; no benchmark problems or answers."""
import json
from pathlib import Path

EXAMPLES = [
 ('stock_value', '재고 딕셔너리의 값은 (수량, 원 단위 단가)입니다. 재고 총액을 반환하는 stock_value(stock) 함수만 작성하세요. 빈 입력은 0입니다.',
  'def stock_value(stock):\n    return sum(quantity * price for quantity, price in stock.values())',
  "assert stock_value({}) == 0\nassert stock_value({'a':(3,120),'b':(2,50)}) == 460"),
 ('discount_won', '정수 가격 price와 0~100의 할인율 percent로 할인 후 가격을 구하는 discount_won(price, percent)를 작성하세요. 소수 원은 버리고 정수를 반환하세요.',
  'def discount_won(price, percent):\n    return price * (100 - percent) // 100',
  'assert discount_won(101,10)==90\nassert discount_won(500,100)==0\nassert discount_won(0,20)==0'),
 ('clean_names', '쉼표로 구분된 이름을 나누는 clean_names(text)를 작성하세요. 따옴표 문법은 없습니다. 양끝 공백을 없애고 빈 항목은 제외하세요.',
  "def clean_names(text):\n    return [part.strip() for part in text.split(',') if part.strip()]",
  "assert clean_names(' A, ,B ,')==['A','B']\nassert clean_names('')==[]"),
 ('duration_label', '0 이상 정수 초 seconds를 분:초 문자열로 바꾸는 duration_label(seconds)를 작성하세요. 두 부분 모두 최소 두 자리이며 3600초는 60:00입니다.',
  "def duration_label(seconds):\n    minutes, remainder = divmod(seconds, 60)\n    return f'{minutes:02d}:{remainder:02d}'",
  "assert duration_label(0)=='00:00'\nassert duration_label(75)=='01:15'\nassert duration_label(3600)=='60:00'"),
 ('has_extension', '파일 이름이 지정 확장자로 끝나는지 확인하는 has_extension(name, extension)을 작성하세요. extension에는 점이 없고 대소문자는 무시하세요.',
  "def has_extension(name, extension):\n    return name.casefold().endswith('.' + extension.casefold())",
  "assert has_extension('Photo.JPG','jpg')\nassert not has_extension('photojpg','jpg')\nassert not has_extension('a.jpg.tmp','jpg')"),
 ('ensure_suffix', '문자열 끝에 suffix가 없을 때만 붙이는 ensure_suffix(text, suffix)를 작성하세요. 빈 suffix는 원문을 그대로 반환하세요.',
  'def ensure_suffix(text, suffix):\n    return text if text.endswith(suffix) else text + suffix',
  "assert ensure_suffix('x.txt','.txt')=='x.txt'\nassert ensure_suffix('x','.txt')=='x.txt'\nassert ensure_suffix('x','')=='x'"),
 ('clamp_score', '정수 점수를 닫힌 구간 [low, high]로 제한하는 clamp_score(score, low, high)를 작성하세요. low <= high입니다.',
  'def clamp_score(score, low, high):\n    return min(high, max(low, score))',
  'assert clamp_score(-3,0,10)==0\nassert clamp_score(7,0,10)==7\nassert clamp_score(30,0,10)==10'),
 ('totals_by_tag', 'events는 (태그, 정수 금액) 쌍들의 리스트입니다. 태그별 합계를 새 딕셔너리로 반환하는 totals_by_tag(events)를 작성하세요. 입력은 수정하지 마세요.',
  'def totals_by_tag(events):\n    totals = {}\n    for tag, amount in events:\n        totals[tag] = totals.get(tag, 0) + amount\n    return totals',
  "assert totals_by_tag([])=={}\nx=[('a',3),('b',4),('a',-1)]\nassert totals_by_tag(x)=={'a':2,'b':4}\nassert x==[('a',3),('b',4),('a',-1)]"),
]


def build_records():
    records = []
    for name, prompt, code, tests in EXAMPLES:
        records.append({'id': name, 'kind': 'coding', 'messages': [
            {'role': 'user', 'content': prompt},
            {'role': 'assistant', 'content': '```python\n' + code + '\n```'}],
            'reference_source': code, 'checks': tests})
    records.extend([
        {'id': 'latest_correction', 'kind': 'conversation', 'messages': [
            {'role': 'user', 'content': '예시 주문 수량은 18개야.'},
            {'role': 'assistant', 'content': '예시 주문 수량은 18개입니다.'},
            {'role': 'user', 'content': '아니, 23개로 바꿔.'},
            {'role': 'assistant', 'content': '23개로 변경했습니다.'},
            {'role': 'user', 'content': '지금 수량이 얼마야?'},
            {'role': 'assistant', 'content': '23개입니다.'}]},
        {'id': 'direct_followup', 'kind': 'conversation', 'messages': [
            {'role': 'user', 'content': 'Python 리스트와 튜플의 차이를 알려줘.'},
            {'role': 'assistant', 'content': '리스트는 원소를 바꿀 수 있고, 튜플은 생성 후 원소를 바꿀 수 없습니다.'},
            {'role': 'user', 'content': '그럼 나중에 항목을 추가할 때는?'},
            {'role': 'assistant', 'content': '리스트를 사용하면 append로 항목을 추가할 수 있습니다.'}]},
    ])
    return records


if __name__ == '__main__':
    from sandbox_eval import Sandbox
    from coding_workflow import check_source, resource_guard
    resource_guard()
    sandbox = Sandbox()
    records = build_records()
    for record in records:
        if record['kind'] == 'coding':
            result = check_source(record['reference_source'], sandbox, record['checks'], record['id'])
            if not result['tests_passed']:
                raise RuntimeError(record['id'] + ': ' + str(result))
    folder = Path(__file__).resolve().parent / 'data/text-training'
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / 'teaching-corpus-v1.jsonl'
    if output.exists():
        raise SystemExit('Teaching corpus already exists; not overwritten')
    output.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
    print('Validated 8 coding references in WASI; 2 authored conversation examples; no benchmark data')
