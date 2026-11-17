import json,time,statistics
from pathlib import Path
from validate_install import chat,get
ROOT=Path(__file__).resolve().parent
report={'requests':[],'samples':[]}
def sample():
    s=get('/status')
    report['samples'].append({'time':time.time(),'ready':s['ready'],'worker_pid':s['worker_pid'],'worker_rss_gb':s['worker_rss_gb'],'system_used_gb':s['system_used_gb'],'available_gb':s['memory']['available_gb'],'restarts':s['restarts']})
    return s
try:
    # Stay idle first: the previous implementation would retain these zero-RSS samples.
    for _ in range(4):sample();time.sleep(.5)
    for i in range(8):
        r=chat([{'role':'user','content':f'파이썬에서 정수 리스트의 합을 구하는 sum_list(nums) 함수를 작성하고 한국어 한 문장으로 설명해 줘. 테스트 번호 {i+1}.'}],128)
        report['requests'].append(r)
        sample()
    baseline=sample();pid=baseline['worker_pid']
    print('Eight requests completed; monitoring loaded worker for 155 seconds',flush=True)
    until=time.monotonic()+155
    while time.monotonic()<until:
        s=sample()
        if not s['ready'] or s['worker_pid']!=pid or s['restarts']!=baseline['restarts']:
            raise AssertionError('Unexpected worker reset: '+json.dumps(s,ensure_ascii=False))
        time.sleep(1)
    final=sample()
    report['final_response']=chat([{'role':'user','content':'한국어로 짧게 답해 줘. 3 더하기 4는 얼마야?'}],32)
    report['summary']={'completed_requests':len(report['requests'])+1,'idle_monitor_seconds':155,'worker_pid_unchanged':True,
        'restarts':final['restarts']-baseline['restarts'],'rss_at_idle_start_gib':baseline['worker_rss_gb'],'rss_at_idle_end_gib':final['worker_rss_gb'],
        'maximum_worker_rss_gib':max(x['worker_rss_gb'] for x in report['samples']),
        'minimum_available_gib':min(x['available_gb'] for x in report['samples']),'final_status':get('/status')}
    print(json.dumps(report['summary'],ensure_ascii=True,indent=2),flush=True)
except Exception as exc:
    report['error']=repr(exc);raise
finally:
    (ROOT/'memory-fix-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
