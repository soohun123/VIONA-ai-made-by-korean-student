"""Four teaching parts, ten task families and five explicit parameter variants each."""
import json
from pathlib import Path

PARTS={'basics':'기초·경계값','collections':'문자열·자료구조','algorithms':'알고리즘','debugging':'버그 수정'}


def tasks():
    result=[]
    def add(part,family,k,prompt,source,checks,bug=None):
        if bug:prompt+='\n다음 잘못된 구현을 수정하세요:\n```python\n'+bug+'\n```'
        result.append({'id':f'{part}-{family}-{k}','part':part,'family':family,'variant':k,
            'entry_point':family,'prompt':prompt+'\n필요한 import와 함수 전체를 Python 코드 블록 하나로만 출력하세요.',
            'reference_source':source,'checks':checks,'provenance':'independently authored teaching template; not a benchmark task'})
    for k in range(1,6):
        rows=[
          ('price_after_discount',f'price_after_discount(price): 0 이상 정수 가격을 {k*5}% 할인하고 소수 원은 버려 반환하세요.',f'def price_after_discount(price):\n    return price * {100-k*5} // 100',f'assert price_after_discount(0)==0\nassert price_after_discount(101)=={101*(100-k*5)//100}\nassert price_after_discount(1000)=={1000-k*50}',f'def price_after_discount(price):\n    return price * {k*5} // 100'),
          ('bounded_mark',f'bounded_mark(score): 정수 점수를 닫힌 구간 [{-k}, {k*10}]로 제한하세요.',f'def bounded_mark(score):\n    return min({k*10}, max({-k}, score))',f'assert bounded_mark(-100)=={-k}\nassert bounded_mark(0)==0\nassert bounded_mark(999)=={k*10}',f'def bounded_mark(score):\n    return min({-k}, max({k*10}, score))'),
          ('delivery_fee',f'delivery_fee(total): 주문액이 {100*k} 이상이면 0, 미만이면 {10*k}를 반환하세요. 주문액은 0 이상 정수입니다.',f'def delivery_fee(total):\n    return 0 if total >= {100*k} else {10*k}',f'assert delivery_fee(0)=={10*k}\nassert delivery_fee({100*k-1})=={10*k}\nassert delivery_fee({100*k})==0',f'def delivery_fee(total):\n    return 0 if total > {100*k} else {10*k}'),
          ('tax_included',f'tax_included(price): 정수 원 단위 가격에 {k}% 세금을 더하고 소수 원을 버리세요.',f'def tax_included(price):\n    return price * {100+k} // 100',f'assert tax_included(0)==0\nassert tax_included(100)=={100+k}\nassert tax_included(199)=={199*(100+k)//100}',f'def tax_included(price):\n    return price + {k}'),
          ('parcel_count',f'parcel_count(items): 물건 {k+1}개가 한 상자에 들어갑니다. 0 이상 정수 물건 수에 필요한 상자 수를 반환하세요.',f'def parcel_count(items):\n    return (items + {k}) // {k+1}',f'assert parcel_count(0)==0\nassert parcel_count(1)==1\nassert parcel_count({k+1})==1\nassert parcel_count({k+2})==2',f'def parcel_count(items):\n    return items // {k+1}'),
          ('minute_charge',f'minute_charge(seconds): 0 이상 정수 초를 올림한 분 단위로 청구하며 분당 {k*3}원입니다. 0초는 0원입니다.',f'def minute_charge(seconds):\n    return ((seconds + 59) // 60) * {k*3}',f'assert minute_charge(0)==0\nassert minute_charge(1)=={k*3}\nassert minute_charge(60)=={k*3}\nassert minute_charge(61)=={k*6}',f'def minute_charge(seconds):\n    return (seconds // 60) * {k*3}'),
          ('capped_balance',f'capped_balance(balance, added): 두 0 이상 정수의 합을 반환하되 최대 {k*100}으로 제한하세요.',f'def capped_balance(balance, added):\n    return min({k*100}, balance + added)',f'assert capped_balance(0,0)==0\nassert capped_balance(1,2)==3\nassert capped_balance(999,999)=={k*100}',f'def capped_balance(balance, added):\n    return max({k*100}, balance + added)'),
          ('allowed_level',f'allowed_level(level): 정수가 {k} 이상 {k*3} 이하인지 bool로 반환하세요.',f'def allowed_level(level):\n    return {k} <= level <= {k*3}',f'assert allowed_level({k}) is True\nassert allowed_level({k*3}) is True\nassert allowed_level({k-1}) is False\nassert allowed_level({k*3+1}) is False',f'def allowed_level(level):\n    return {k} < level < {k*3}'),
          ('shift_weekday',f'shift_weekday(day): 0~6으로 표현한 요일에서 {k}일 뒤 요일을 0~6으로 반환하세요.',f'def shift_weekday(day):\n    return (day + {k}) % 7',f'assert shift_weekday(0)=={k%7}\nassert shift_weekday(6)=={(6+k)%7}\nassert shift_weekday(3)=={(3+k)%7}',f'def shift_weekday(day):\n    return (day + {k}) % 6'),
          ('affordable_units',f'affordable_units(budget): 0 이상 정수 예산으로 개당 {k*7}원인 물건을 최대 몇 개 살 수 있는지 반환하세요.',f'def affordable_units(budget):\n    return budget // {k*7}',f'assert affordable_units(0)==0\nassert affordable_units({k*7-1})==0\nassert affordable_units({k*21})==3',f'def affordable_units(budget):\n    return budget * {k*7}'),
        ]
        for name,prompt,source,checks,bug in rows:
            add('basics',name,k,prompt,source,checks)
            add('debugging',name,k,prompt,source,checks,bug)
        suffix=f'.part{k}'
        collections=[
          ('strip_part_suffix',f'strip_part_suffix(text): 끝에 {suffix!r}가 있으면 그 접미사 하나만 제거하세요.',f'def strip_part_suffix(text):\n    return text[:-{len(suffix)}] if text.endswith({suffix!r}) else text',f'assert strip_part_suffix("x{suffix}")=="x"\nassert strip_part_suffix("{suffix}x")=="{suffix}x"\nassert strip_part_suffix("")==""'),
          ('long_names',f'long_names(names): 길이가 {k} 이상인 문자열만 원래 순서의 새 리스트로 반환하세요.',f'def long_names(names):\n    return [name for name in names if len(name) >= {k}]',f'assert long_names([])==[]\nassert long_names(["", "abcdef", "xy"])=={[x for x in ("","abcdef","xy") if len(x)>=k]!r}'),
          ('repeat_values',f'repeat_values(values): 각 원소를 연속 {k}번씩 반복한 새 리스트를 반환하세요. 원본을 바꾸지 마세요.',f'def repeat_values(values):\n    return [value for value in values for _ in range({k})]',f'assert repeat_values([])==[]\nx=[1,2];assert repeat_values(x)=={[1]*k+[2]*k};assert x==[1,2]'),
          ('tag_total',f'tag_total(events): (태그, 금액) 쌍에서 태그가 "p{k}"인 금액만 더하세요.',f'def tag_total(events):\n    return sum(amount for tag, amount in events if tag == "p{k}")',f'assert tag_total([])==0\nassert tag_total([("p{k}",3),("other",99),("p{k}",-1)])==2'),
          ('join_labels',f'join_labels(labels): 문자열들을 {str(k)!r} 구분자로 연결하세요. 빈 입력은 빈 문자열입니다.',f'def join_labels(labels):\n    return {str(k)!r}.join(labels)',f'assert join_labels([])==""\nassert join_labels(["a","b"])=="a{k}b"'),
          ('prefix_items',f'prefix_items(items): 각 문자열 앞에 "v{k}:"를 붙인 새 리스트를 반환하세요.',f'def prefix_items(items):\n    return ["v{k}:" + item for item in items]',f'assert prefix_items([])==[]\nassert prefix_items(["","x"])==["v{k}:","v{k}:x"]'),
          ('first_words',f'first_words(text): 공백으로 나눈 처음 {k}개 단어를 리스트로 반환하세요. 연속 공백을 무시하세요.',f'def first_words(text):\n    return text.split()[:{k}]',f'assert first_words("")==[]\nassert first_words(" a  b c d e f ")=={list("abcdef")[:k]!r}'),
          ('letter_frequency',f'letter_frequency(text): 문자 {chr(96+k)!r}의 등장 횟수를 대소문자 무시하고 반환하세요.',f'def letter_frequency(text):\n    return text.casefold().count({chr(96+k)!r})',f'assert letter_frequency("")==0\nassert letter_frequency("{chr(96+k)}{chr(64+k)}z")==2'),
          ('chunks_of_values',f'chunks_of_values(values): 리스트를 최대 {k}개씩 묶은 새 리스트들의 리스트로 반환하세요. 마지막 나머지도 보존하세요.',f'def chunks_of_values(values):\n    return [values[i:i+{k}] for i in range(0,len(values),{k})]',f'assert chunks_of_values([])==[]\nassert chunks_of_values([1,2,3,4,5,6])=={[list(range(1,7))[i:i+k] for i in range(0,6,k)]!r}'),
          ('numbered_labels',f'numbered_labels(labels): 각 문자열에 {k}부터 시작하는 번호를 붙인 (번호, 문자열) 튜플 리스트를 반환하세요.',f'def numbered_labels(labels):\n    return list(enumerate(labels,{k}))',f'assert numbered_labels([])==[]\nassert numbered_labels(["a","b"])==[({k},"a"),({k+1},"b")]'),
        ]
        for row in collections:add('collections',row[0],k,*row[1:])
        algorithms=[
          ('offset_prefix_sums',f'offset_prefix_sums(values): 초기 합 {k}에서 시작해 각 원소까지 더한 누적합 리스트를 반환하세요.',f'def offset_prefix_sums(values):\n    total={k}\n    result=[]\n    for value in values:\n        total+=value\n        result.append(total)\n    return result',f'assert offset_prefix_sums([])==[]\nassert offset_prefix_sums([2,-3,4])==[{k+2},{k-1},{k+3}]'),
          ('rotate_left',f'rotate_left(values): 리스트를 왼쪽으로 {k}칸 회전한 새 리스트를 반환하세요. 빈 입력을 지원하세요.',f'def rotate_left(values):\n    if not values: return []\n    amount={k}%len(values)\n    return values[amount:]+values[:amount]',f'assert rotate_left([])==[]\nassert rotate_left([1,2,3])=={[1,2,3][k%3:]+[1,2,3][:k%3]}'),
          ('window_totals',f'window_totals(values): 연속 {k}개짜리 각 완전한 창의 합을 반환하세요. 입력보다 창이 크면 빈 리스트입니다.',f'def window_totals(values):\n    if len(values)<{k}: return []\n    total=sum(values[:{k}]);result=[total]\n    for i in range({k},len(values)):\n        total+=values[i]-values[i-{k}]\n        result.append(total)\n    return result',f'assert window_totals([])==[]\nassert window_totals([1,2,3,4,5,6])=={[sum(list(range(1,7))[i:i+k]) for i in range(7-k)]}'),
          ('lower_insertion',f'lower_insertion(values): 오름차순 리스트에서 값 {k}를 넣을 첫 위치를 이진 탐색으로 반환하세요. 중복 앞에 삽입합니다.',f'def lower_insertion(values):\n    lo,hi=0,len(values)\n    while lo<hi:\n        mid=(lo+hi)//2\n        if values[mid]<{k}: lo=mid+1\n        else: hi=mid\n    return lo',f'assert lower_insertion([])==0\nassert lower_insertion([{k},{k},{k+1}])==0\nassert lower_insertion([{k-2},{k-1},{k+1}])==2'),
          ('row_target_counts',f'row_target_counts(rows): 길이가 서로 다른 각 행에서 값 {k}의 등장 횟수를 행 순서대로 반환하세요.',f'def row_target_counts(rows):\n    return [row.count({k}) for row in rows]',f'assert row_target_counts([])==[]\nassert row_target_counts([[],[{k},{k}],[-99]])==[0,2,0]'),
          ('running_target_counts',f'running_target_counts(values): 앞에서 현재 위치까지 값 {k}가 나온 누적 횟수 리스트를 반환하세요.',f'def running_target_counts(values):\n    count=0;result=[]\n    for value in values:\n        if value=={k}: count+=1\n        result.append(count)\n    return result',f'assert running_target_counts([])==[]\nassert running_target_counts([{k},-99,{k}])==[1,1,2]'),
          ('threshold_runs',f'threshold_runs(values): {k} 이상 값들이 연속되는 각 구간 길이를 순서대로 반환하세요. 마지막 구간도 포함하세요.',f'def threshold_runs(values):\n    result=[];count=0\n    for value in values:\n        if value>={k}:count+=1\n        elif count:result.append(count);count=0\n    if count:result.append(count)\n    return result',f'assert threshold_runs([])==[]\nassert threshold_runs([{k},{k+1},-99,{k}])==[2,1]\nassert threshold_runs([-99])==[]'),
          ('limited_flatten',f'limited_flatten(rows): 중첩 리스트를 행 순서로 펼친 처음 {k}개 원소를 반환하세요. 행 길이는 다를 수 있습니다.',f'def limited_flatten(rows):\n    result=[]\n    for row in rows:\n        for value in row:\n            if len(result)=={k}:return result\n            result.append(value)\n    return result',f'assert limited_flatten([])==[]\nassert limited_flatten([[],[1,2],[3,4,5,6]])=={list(range(1,7))[:k]}'),
          ('adjacent_gaps',f'adjacent_gaps(values): 인접 원소 차이가 {k} 이상인 오른쪽 원소의 인덱스를 순서대로 반환하세요.',f'def adjacent_gaps(values):\n    return [i for i in range(1,len(values)) if values[i]-values[i-1]>={k}]',f'assert adjacent_gaps([])==[]\nassert adjacent_gaps([0,{k},{k-1},{3*k}])==[1,3]'),
          ('closest_capacity',f'closest_capacity(values): {k*10}을 넘지 않는 가장 큰 정수를 반환하세요. 해당 값이 없으면 None입니다.',f'def closest_capacity(values):\n    result=None\n    for value in values:\n        if value<={k*10} and (result is None or value>result):result=value\n    return result',f'assert closest_capacity([]) is None\nassert closest_capacity([{k*10+1}]) is None\nassert closest_capacity([-2,{k*10},{k*10+1}])=={k*10}'),
        ]
        for row in algorithms:add('algorithms',row[0],k,*row[1:])
    assert len(result)==200 and len({r['id'] for r in result})==200
    return sorted(result,key=lambda r:(list(PARTS).index(r['part']),r['variant'],r['family']))


if __name__=='__main__':
    from sandbox_eval import Sandbox
    from coding_workflow import check_source
    sandbox=Sandbox();rows=tasks()
    for i,row in enumerate(rows):
        checked=check_source(row['reference_source'],sandbox,row['checks'],row['entry_point'])
        if not checked['tests_passed']:raise RuntimeError(row['id']+': '+str(checked))
        if (i+1)%50==0:print('VERIFIED',i+1,flush=True)
    directory=Path(__file__).resolve().parent/'data/coding-learning';directory.mkdir(parents=True,exist_ok=True)
    path=directory/'curriculum-v1.jsonl'
    if path.exists():raise SystemExit('Existing curriculum not overwritten')
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    print('200 reference implementations verified in WASI')
