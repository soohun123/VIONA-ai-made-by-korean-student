"""Controlled conversation contexts; actual model responses, no generated-code execution."""
import json,time,urllib.request,argparse
from pathlib import Path
CASES=[
 ('remember_name',[{'role':'user','content':'내가 만드는 프로그램의 이름은 노바야. 기억해 줘.'},{'role':'assistant','content':'프로그램 이름은 노바입니다. 기억하겠습니다.'},{'role':'user','content':'내 프로그램 이름이 뭐야? 이름만 답해.'}],'노바'),
 ('topic_change',[{'role':'user','content':'비행기의 양력을 설명해 줘.'},{'role':'assistant','content':'양력은 날개 주변의 압력 차이와 공기의 운동량 변화로 발생합니다.'},{'role':'user','content':'이제 다른 질문이야. 17 곱하기 23은? 결과 숫자만 답해.'}],'391'),
 ('followup_correction',[{'role':'user','content':'He go to school every day. 이 문장 문법을 교정해 줘.'},{'role':'assistant','content':'He goes to school every day. 주어가 3인칭 단수이므로 goes를 씁니다.'},{'role':'user','content':'설명은 빼고 방금 교정한 영어 문장만 다시 써 줘.'}],'He goes to school every day.'),
 ('direct_comparison',[{'role':'user','content':'앞으로 컴퓨터에 대해 질문할게.'},{'role':'assistant','content':'컴퓨터에 관한 질문에 답하겠습니다.'},{'role':'user','content':'RAM과 SSD의 차이는? 대화를 요약하지 말고 두 가지 차이만 한국어로 답해.'}],None)
]
def run():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    results=[]
    for name,messages,expected in CASES:
        payload={'messages':messages,'max_tokens':192,'temperature':0,'top_p':1,'enhance':True,'skill':'auto','search_mode':'auto'}
        req=urllib.request.Request('http://127.0.0.1:8000/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        item={'name':name,'messages':messages,'expected_fragment':expected,'started':time.time(),'response':'','context':None}
        try:
            with urllib.request.urlopen(req,timeout=180) as response:
                for line in response:
                    msg=json.loads(line)
                    if msg.get('kind')=='context':item['context']=msg
                    if msg.get('token'):item['response']+=msg['token']
                    if msg.get('done'):item['metrics']=msg['metrics']
                    if msg.get('error'):item['error']=msg['error']
            item['surface_check']=expected.lower() in item['response'].lower() if expected else None
        except Exception as e:item['error']=repr(e)
        item['elapsed']=time.time()-item['started'];results.append(item)
        Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,json.dumps(item['response'],ensure_ascii=True),'check',item.get('surface_check'),flush=True)
if __name__=='__main__':run()
