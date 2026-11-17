"""Seeded random word probes. All raw model outputs retained; no generated code execution."""
import argparse,json,random,time,urllib.request
from pathlib import Path
WORDS=['사과','항공','GPU','문법','바나나','헬리콥터','세종대왕','왜','ㅋㅋㅋ','안녕','블루베리','양자','컴퓨터','갑자기','비행기','바람','return','초콜릿','퀵정렬','달']
def run():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    words=random.Random(20261114).sample(WORDS,8)+['뭉라토즈']
    cases=[{'name':word,'messages':[{'role':'user','content':word}]} for word in words]
    cases += [{'name':'topic_switch_GPU','messages':[{'role':'user','content':'된장찌개에 대해 설명해 줘.'},{'role':'assistant','content':'된장찌개는 된장을 풀어 채소와 두부 등을 넣고 끓이는 음식입니다.'},{'role':'user','content':'GPU'}]}, {'name':'contextual_why','messages':[{'role':'user','content':'물은 왜 얼어?'},{'role':'assistant','content':'온도가 낮아지면 물 분자들이 일정한 구조를 이루며 고체인 얼음으로 변합니다.'},{'role':'user','content':'왜?'}]}]
    results=[]
    for case in cases:
        payload={**case,'max_tokens':160,'temperature':0,'top_p':1,'enhance':True,'skill':'auto','search_mode':'auto'}
        req=urllib.request.Request('http://127.0.0.1:8000/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        item={**case,'response':'','started':time.time()}
        try:
            with urllib.request.urlopen(req,timeout=180) as response:
                for line in response:
                    msg=json.loads(line)
                    if msg.get('kind')=='context':item['context']=msg
                    if msg.get('token'):item['response']+=msg['token']
                    if msg.get('done'):item['metrics']=msg['metrics']
                    if msg.get('error'):item['error']=msg['error']
        except Exception as exc:item['error']=repr(exc)
        item['elapsed']=time.time()-item['started'];results.append(item)
        Path(args.output).write_text(json.dumps({'seed':20261114,'random_words':words,'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
        print(case['name'],json.dumps(item['response'],ensure_ascii=True),'error',item.get('error'),flush=True)
if __name__=='__main__':run()
