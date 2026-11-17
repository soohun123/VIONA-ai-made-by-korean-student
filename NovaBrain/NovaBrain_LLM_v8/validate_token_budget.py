"""Compare actual model requests using identical long conversations and tokenizer proxy."""
import json,time,urllib.request
from pathlib import Path
from validate_install import get
ROOT=Path(__file__).resolve().parent
def chat(messages,profile,plugin=''):
    payload={'messages':messages,'enhance':True,'max_tokens':128,'temperature':0,'top_p':1,'search_mode':'off','token_profile':profile,'plugin_id':plugin}
    req=urllib.request.Request('http://127.0.0.1:8000/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    result={'profile':profile,'response':''};start=time.perf_counter()
    with urllib.request.urlopen(req,timeout=180) as response:
        for line in response:
            event=json.loads(line)
            if event.get('kind')=='context':result['context']=event
            if event.get('token'):result['response']+=event['token']
            if event.get('done'):result['metrics']=event['metrics']
            if event.get('error'):raise RuntimeError(event['error'])
    result['elapsed']=time.perf_counter()-start
    return result
messages=[{'role':'user','content':'내 프로젝트 이름은 별빛노트이고 사용 언어는 파이썬이야. 기억해.'},{'role':'assistant','content':'프로젝트 이름은 별빛노트, 언어는 파이썬입니다.'}]
for i in range(14):
    messages += [{'role':'user','content':f'연습 {i}의 짧은 설명을 부탁해.'}, {'role':'assistant','content':('이 내용은 연습용 대화입니다. 다음 질문을 기다립니다. '*6)}]
messages.append({'role':'user','content':'내 프로젝트 이름과 사용 언어를 한국어 한 문장으로 답해.'})
full=chat(messages,'full');economy=chat(messages,'economy')
code=chat([{'role':'user','content':'파이썬 함수 add(a, b)를 작성해 줘. 두 수를 더해서 반환하면 돼. 함수 코드만, 설명이나 다른 함수 없이.'}],'economy','minimal-code')
result={'full':full,'economy':economy,'minimal_code':code,'token_measurement':'JSON tokenizer + per-message reserve; same proxy in both requests, not exact chat-template or billed API tokens',
        'input_proxy_reduction_percent':100*(1-economy['metrics']['input_proxy_tokens']/full['metrics']['input_proxy_tokens']),
        'economy_remembers_project':'별빛노트' in economy['response'],'economy_remembers_language':'파이썬' in economy['response'],
        'minimal_code_has_requested_function':'def add(' in code['response'],'minimal_code_extra_functions':max(0,code['response'].count('def ')-1),'status':get('/status')}
(ROOT/'token-budget-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
