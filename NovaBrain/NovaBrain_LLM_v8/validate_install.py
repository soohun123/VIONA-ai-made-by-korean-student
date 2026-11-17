"""Five real-model coding tasks, executed only inside offline WASI Python."""
import json,re,time,threading,urllib.request,statistics
from pathlib import Path
import psutil
from sandbox_eval import Sandbox
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8000'
def get(path):
    with urllib.request.urlopen(URL+path,timeout=10) as r:return json.load(r)
def chat(messages,max_tokens=512):
    payload={'messages':messages,'max_tokens':max_tokens,'temperature':0,'top_p':1}
    req=urllib.request.Request(URL+'/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    start=time.perf_counter();events=[];parts=[];metrics=None
    with urllib.request.urlopen(req,timeout=600) as r:
        for line in r:
            msg=json.loads(line)
            if 'error' in msg:raise RuntimeError(msg['error'])
            if msg.get('token'):parts.append(msg['token']);events.append(time.perf_counter()-start)
            if msg.get('done'):metrics=msg.get('metrics')
    if metrics is None:raise RuntimeError('Stream ended without done')
    return {'reply':''.join(parts),'metrics':metrics,'stream_events':len(events),'first_event_seconds':events[0] if events else None,'last_event_seconds':events[-1] if events else None}
TASKS=[
 ('sum_even','정수 리스트 nums에서 짝수만 더하는 sum_even(nums) 함수를 작성해 줘. 빈 리스트는 0을 반환해.',"assert sum_even([])==0\nassert sum_even([1,2,3,4])==6\nassert sum_even([-4,-3,0,8])==4\nassert sum_even([1,3,5])==0"),
 ('fibonacci','0 이상의 정수 n에 대해 F(0)=0, F(1)=1인 피보나치 수를 반환하는 fibonacci(n) 함수를 작성해 줘. 반복문을 사용해.',"assert [fibonacci(i) for i in range(11)]==[0,1,1,2,3,5,8,13,21,34,55]\nassert fibonacci(30)==832040"),
 ('is_balanced','문자열 s의 괄호 (), [], {}가 올바르게 짝지어지고 중첩되었는지 bool을 반환하는 is_balanced(s) 함수를 작성해 줘. 일반 문자는 무시하고 빈 문자열은 True로 처리해.',"assert is_balanced('')\nassert is_balanced('a{b[c(d)]}')\nassert not is_balanced('([)]')\nassert not is_balanced(']')\nassert not is_balanced('(()')"),
 ('merge_intervals','[시작,끝] 리스트들의 리스트 intervals를 받아 겹치거나 끝점이 닿는 구간을 합쳐 정렬된 리스트를 반환하는 merge_intervals(intervals) 함수를 작성해 줘. 빈 입력을 지원하고 원본 리스트를 변경하지 마.',"assert merge_intervals([])==[]\nassert merge_intervals([[1,3],[2,6],[8,10],[15,18]])==[[1,6],[8,10],[15,18]]\nassert merge_intervals([[1,4],[4,5]])==[[1,5]]\nx=[[5,7],[1,10],[2,3]]; old=[a[:] for a in x]; assert merge_intervals(x)==[[1,10]]; assert x==old"),
 ('binary_search','오름차순 정수 리스트 nums에서 target의 인덱스를 반환하고 없으면 -1인 binary_search(nums,target) 함수를 이진 탐색으로 작성해 줘. 원소는 서로 달라.',"assert binary_search([],1)==-1\nassert binary_search([1],1)==0\nassert binary_search([1],2)==-1\na=[-5,-1,0,3,8,11]; assert all(binary_search(a,v)==i for i,v in enumerate(a))\nassert binary_search(a,5)==-1")]
def main():
    result={'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'tasks':[],'samples':[]}
    done=threading.Event()
    def monitor():
        psutil.cpu_percent(None)
        while not done.wait(.25):
            m=psutil.virtual_memory()
            result['samples'].append({'time':time.time(),'system_used_gib':m.used/2**30,'available_gib':m.available/2**30,'system_cpu_percent':psutil.cpu_percent(None)})
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        result['korean']=chat([{'role':'system','content':'너는 NovaBrain이라는 한국어 로컬 AI야. 한국어로 짧게 대답해.'},{'role':'user','content':'안녕! 네가 할 수 있는 일을 한국어 두 문장으로 알려줘.'}],160)
        sandbox=Sandbox()
        result['sandbox_checks']={
            'normal':sandbox.run("print('OK')"),
            'network_blocked':sandbox.run("import socket; socket.socket().connect(('1.1.1.1',443))"),
            'write_blocked':sandbox.run("open('/usr/local/lib/probe-write','w')"),
            'host_fs_blocked':sandbox.run("open('/host-secret').read()"),
            'timeout':sandbox.run('while True: pass',1)}
        for name,prompt,checks in TASKS:
            output=chat([{'role':'system','content':'You are a Python coding assistant. Return only the complete requested Python function. No explanations. Use the Python standard library.'},{'role':'user','content':prompt}],768)
            code=output['reply'].strip()
            fences=re.findall(r'```(?:python)?\s*\n(.*?)```',code,re.S)
            if fences:code='\n\n'.join(fences)
            checked=sandbox.run(code+'\n'+checks+"\nprint('ALL_ASSERTIONS_PASSED')")
            output.update({'name':name,'prompt':prompt,'code':code,'evaluation':checked})
            result['tasks'].append(output)
            (ROOT/'validation-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(name,'PASS' if checked['passed'] else 'FAIL',round(output['metrics']['tokens_per_second'],2),'tok/s',flush=True)
        before=get('/status')
        pid=before['worker_pid']
        if not pid:raise RuntimeError('No worker to test recovery')
        psutil.Process(pid).terminate()
        time.sleep(1.5)
        result['recovery_test']={'terminated_worker_pid':pid,'before':before,
            'reply':chat([{'role':'user','content':'파이썬에서 2+3의 결과는? 짧게 답해.'}],64),'after':get('/status')}
        outputs=[x['metrics'] for x in result['tasks']]
        samples=result['samples']
        result['summary']={'passed':sum(x['evaluation']['passed'] for x in result['tasks']),'total':len(TASKS),
            'accuracy_percent':100*sum(x['evaluation']['passed'] for x in result['tasks'])/len(TASKS),
            'mean_tokens_per_second':statistics.mean(x['tokens_per_second'] for x in outputs),
            'weighted_tokens_per_second':sum(x['output_tokens'] for x in outputs)/sum(x['elapsed_seconds'] for x in outputs),
            'mean_decode_tokens_per_second':statistics.mean(x['decode_tokens_per_second'] for x in outputs),
            'peak_system_used_gib':max(x['system_used_gib'] for x in samples),
            'minimum_available_gib':min(x['available_gib'] for x in samples),
            'mean_system_cpu_percent':statistics.mean(x['system_cpu_percent'] for x in samples),
            'peak_system_cpu_percent':max(x['system_cpu_percent'] for x in samples),
            'status':get('/status')}
    except Exception as exc:
        result['fatal_error']=repr(exc)
        raise
    finally:
        done.set();thread.join(timeout=2)
        (ROOT/'validation-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
