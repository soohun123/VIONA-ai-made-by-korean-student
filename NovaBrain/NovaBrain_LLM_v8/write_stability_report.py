import json,statistics,hashlib,time
from pathlib import Path
from validate_install import get
ROOT=Path(__file__).resolve().parent
r=json.loads((ROOT/'stability-validation.json').read_text(encoding='utf-8'))
h=json.loads((ROOT/'humaneval/results.json').read_text(encoding='utf-8'))
audit=json.loads((ROOT/'humaneval/format-audit.json').read_text(encoding='utf-8'))
ui=json.loads((ROOT/'ui-validation.json').read_text(encoding='utf-8'))
idle=json.loads((ROOT/'post-eval-idle.json').read_text(encoding='utf-8'))
s=r['samples'];summary={}
for group in ('server','worker'):
    summary[group]={}
    for metric in ('rss','private','handles','threads','cpu_machine_percent'):
        values=[x[group][metric] for x in s]
        summary[group][metric]={'start':values[0],'maximum':max(values),'end':values[-1],'mean':statistics.mean(values)}
    summary[group]['process_count']={'start':len(s[0][group]['pids']),'maximum':max(len(x[group]['pids']) for x in s),'end':len(s[-1][group]['pids'])}
same=[x for x in s if x['worker_pid']==s[-1]['worker_pid'] and x['ready']]
summary['last_worker']={'seconds':same[-1]['time']-same[0]['time'],'rss_delta':same[-1]['worker']['rss']-same[0]['worker']['rss'],'private_delta':same[-1]['worker']['private']-same[0]['worker']['private'],'handles_start':same[0]['worker']['handles'],'handles_end':same[-1]['worker']['handles']}
metrics=[x['metrics'] for x in r['requests']]
summary.update({'elapsed_seconds':r['elapsed_seconds'],'completed_requests':len(metrics),'interrupted_requests':4,'intentional_launcher_crashes':1,'minimum_available_gib':min(x['available'] for x in s)/2**30,'maximum_used_gib':max(x['used'] for x in s)/2**30,'weighted_tokens_per_second':sum(x['output_tokens'] for x in metrics)/sum(x['elapsed_seconds'] for x in metrics),'errors':r['final_status']['errors'],'restarts':r['final_status']['restarts'],'recoveries':r['final_status']['recoveries']})
rows=[json.loads(x) for x in (ROOT/'humaneval/samples.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(rows)==len({x['task_id'] for x in rows})==164
manifest=json.loads((ROOT/'humaneval/run-manifest.json').read_text(encoding='utf-8'))
first=(ROOT/'humaneval/samples.jsonl').read_bytes().splitlines(keepends=True)[0]
summary['existing_sample_unchanged']=hashlib.sha256(first).hexdigest()==manifest['existing_samples_sha256']
summary['final_status']=get('/status')
summary['post_eval_idle']={k:v for k,v in idle.items() if k!='samples'}
trace=[json.loads(x) for x in (ROOT/'benchmark-resources.jsonl').read_text(encoding='utf-8').splitlines()]
trace=[x for x in trace if 'processes' in x and x['status']['worker_pid']==summary['final_status']['worker_pid'] and x['status']['ready']]
summary['benchmark_resources']={}
for g in ('server','worker'):
    vals=[{k:sum(p[k] or 0 for p in x['processes'][g]) for k in ('rss','private','handles','cpu_machine_percent')} for x in trace]
    summary['benchmark_resources'][g]={k:{'start':vals[0][k],'max':max(v[k] for v in vals),'end':vals[-1][k],'mean':statistics.mean(v[k] for v in vals)} for k in vals[0]}
(ROOT/'stability-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# NovaBrain v8 자원 안정성 및 HumanEval 검증',f'작성: {time.strftime("%Y-%m-%dT%H:%M:%S%z")}','',
'## 발견 및 수정',
'- 실제 재현: 가상환경 워커 런처 PID 14368 종료 후 실제 모델 Python PID 5116이 살아남았으며 기존 /admin/restart 후에도 남았습니다. 해당 설치 경로와 명령을 확인한 자식만 정리했습니다.',
'- server.py: 준비 완료 시 자식 Process 신원(PID와 생성 시각)을 보관합니다. 런처가 이미 종료되어도 자식을 종료하고 기다리며, 강제 종료 후에도 대기합니다. 종료된 워커를 교체하기 전 정리합니다. 종료된 부모 PID로 새 프로세스 트리를 탐색하지 않습니다.',
'- test_memory_guard.py: 부모가 먼저 종료한 경우 자식 회수, 죽은 워커 교체 전 정리 테스트 추가. 기존 8개 포함 총 10개 통과. engine.py, worker.py, 모델 및 생성 로직은 변경하지 않았습니다.',
'- 기존 준비 전 표본 제외, 로딩 기준 초기화, 30초 예열, 예열 후 120초/1GiB 증가 감지 유지. 13GiB 경고·13.5GiB 차단/중단·2GiB 여유 목표 유지. 합성 보호 검사 통과.',
'- 서버 소스 및 기존 평가 자료 백업: ../backups/stability-20261114-173331/. 사용자 모델·대화 기록 삭제 없음.','',
'- 백업 절차 누락: test_memory_guard.py는 수정 전 복사에서 빠졌습니다. 처음 읽은 원본을 기준으로 추가 부분만 역변환한 baseline-reconstructed.py를 따로 보관했고 초기 크기 2,784 bytes와 일치합니다. 이는 사전 백업 파일은 아닙니다. 기존 8개 테스트는 유지했습니다.','',
'## 실제 모델 안정성',
f'- 시작: {r["started_at"]}, 총 {r["elapsed_seconds"]:.1f}초. 완료 생성 {len(metrics)}회, 별도 사용자 취소 2회와 연결 종료 2회, 런처 강제 종료 1회. 중단된 모든 기존 프로세스 생존 0, 다음 생성 복구 성공.',
f'- 관측 오류 {summary["errors"]}회, 의도적 재시작 {summary["restarts"]}회, 복구 {summary["recoveries"]}회. 예기치 않은 재시작 {summary["restarts"]-5}회.',
f'- 출력 토큰/생성 시간: {summary["weighted_tokens_per_second"]:.2f} tokens/s. 시스템 사용 RAM 최대 {summary["maximum_used_gib"]:.3f}GiB, 최소 여유 {summary["minimum_available_gib"]:.3f}GiB.',
'- 1초 간격 측정. 서버는 포트 소유 실제 Python 프로세스(가상환경 부모 런처 제외), 워커는 런처·실제 Python·전용 conhost의 합계. private는 Windows private commit이며 USS 또는 RSS와의 차감값이 아닙니다.','',
'| 대상 | RSS 시작/최대/종료 GiB | Private 시작/최대/종료 GiB | 핸들 시작/최대/종료 | CPU 평균/최대(전체 CPU 용량 %) | 프로세스 시작/최대/종료 |',
'|---|---|---|---|---|---|']
for group,label in [('server','서버'),('worker','워커 트리')]:
    v=summary[group]
    fmt=lambda m,scale=1:'/ '.join(f'{v[m][k]/scale:.3f}' for k in ('start','maximum','end'))
    counts='/'.join(str(v['process_count'][k]) for k in ('start','maximum','end'))
    lines.append(f'| {label} | {fmt("rss",2**30)} | {fmt("private",2**30)} | {fmt("handles")} | {v["cpu_machine_percent"]["mean"]:.2f}/{v["cpu_machine_percent"]["maximum"]:.2f} | {counts} |')
last=summary['last_worker']
lines += ['',f'- 마지막 동일 워커 관측 {last["seconds"]:.1f}초: RSS 변화 {last["rss_delta"]/2**20:.2f}MiB, private 변화 {last["private_delta"]/2**20:.2f}MiB, 핸들 {last["handles_start"]}→{last["handles_end"]}.',
'- model.gguf mmap 상주량 1,117,323,264 bytes를 Windows memory_maps에서 확인했습니다(memory-mappings.json). RSS는 mmap 페이지 인과 KV/연산 버퍼, 런타임 캐시를 포함하므로 로딩 전 0과 비교해 누수라고 판정하지 않습니다. 요청 후 유지되는 수 MiB 캐시와 자식 잔류를 구분했습니다. 이번 구간에서 지속적 누수 증거는 관측되지 않았지만 수 시간·수 일, 긴 대화·최대 컨텍스트 누수 부재를 증명하지 않습니다.','',
'## 추가 복구 및 PC·모바일',
'- 안정성 검사 후 최신 디스크 소스로 서버 재시작, 회귀 테스트 재실행. UI 한국어 응답, 스트리밍 DOM 갱신, 새로고침 기록 유지, JSON 내보내기, 취소, 모바일 코드 생성과 복구 통과. 390×844 가로 넘침 없음. JavaScript 오류 '+str(len(ui['errors']))+'회.',
'- 실제 모델 Python 자식 강제 종료 후 기존 워커 트리 회수와 다음 응답 복구도 별도 통과(native-worker-recovery.json).',
'- Browser 플러그인은 native pipe bridge 오류로 연결 불가. 기존 격리 headless Edge 테스트 사용. 사용자 실제 포인터·키보드 포커스·클립보드를 조작하지 않았습니다. 화면 PNG 별도 확인. 물리 iPhone/Safari는 미검증.','',
'## HumanEval',
f'- 공식 164문제 중 {h["completed"]}문제 평가 완료, 정답 {h["passed"]}/164, 실제 pass@1 = {h["full_humaneval_pass_at_1"]:.6f} ({100*h["full_humaneval_pass_at_1"]:.2f}%).',
'- WASI CPython 3.11.4/Wasmtime 결과이며 공식 native CPython 실행 결과와 런타임 차이가 있습니다.',
f'- 중요한 해석 제한: 함수 본문만 요청했으나 {audit["repeated_signature_at_start"]}개 응답이 함수 선언을 다시 출력했습니다. 기존 정규화가 이를 원래 함수 내부의 중첩 정의로 만들며 해당 샘플은 모두 실패했습니다. 이는 출력 형식 준수까지 포함한 기존 본문 완성 프로토콜 점수이며, 전체 함수 추출 방식으로 평가한 순수 코딩 점수는 측정하지 않았습니다. 원시 응답이나 최초 점수는 변경하지 않았습니다.',
f'- 실패 분류: assertion {audit["failure_categories"]["assertion"]}, 기타 실행 오류 {audit["failure_categories"]["runtime"]}, 문법 오류 {audit["failure_categories"]["syntax"]}, 시간 초과 {audit["failure_categories"].get("timeout",0)}. 출력 한도 도달 샘플 {audit["token_limit_samples"]}개. HumanEval 출력/생성 시간 {audit["weighted_tokens_per_second"]:.2f} tokens/s. 자세한 형식 감사: humaneval/format-audit.json.',
'- 기존 HumanEval/0 한 샘플은 설치 보고서·기존 결과·변경되지 않은 생성 소스로 조건 일치를 확인하고 재사용. 독립적인 당시 per-sample manifest는 없다는 한계를 run-manifest.json에 기록했습니다. 원래 샘플 해시 일치: '+str(summary['existing_sample_unchanged'])+'. 나머지 163개 각 한 번 생성, 중복·재시도·정답 선택·로직 수정 없음.',
'- temperature=0, top_p=1, seed=42, max_tokens=1024, context=8192, CPU 6 threads, GPU=0. Markdown 제거와 들여쓰기 정규화만 기존 도구 그대로 적용. 잘림·문법·논리 오답도 그대로 집계.',
'- 네트워크 미제공, 읽기 전용 stdlib, 호스트 경로 차단, 256MiB 선형 메모리, 문제당 10초 제한 유지. 정상 실행/네트워크/쓰기/호스트 경로/무한 루프 재검증(sandbox-recheck.jsonl). 생성 코드는 호스트 Python에서 실행하지 않았습니다.','',
'## 전체 평가 구간 및 평가 후 유휴 관측',
f'- 평가 중 마지막 동일 워커 자원 표본 {len(trace)}개. 상세 시작·최대·종료 RSS/private/핸들/CPU는 stability-summary.json의 benchmark_resources와 benchmark-resources.jsonl에 기록했습니다.',
f'- 평가 후 {idle["seconds"]:.1f}초 동안 같은 워커 PID {idle["worker_pid"]}, ready와 재시작 횟수 유지. 새 생성 없이 관찰했습니다.',
f'- 워커 RSS 시작/최대/종료: {idle["summary"]["rss"]["start"]/2**30:.4f}/{idle["summary"]["rss"]["max"]/2**30:.4f}/{idle["summary"]["rss"]["end"]/2**30:.4f}GiB. Private: {idle["summary"]["private"]["start"]/2**30:.4f}/{idle["summary"]["private"]["max"]/2**30:.4f}/{idle["summary"]["private"]["end"]/2**30:.4f}GiB. 핸들: {idle["summary"]["handles"]["start"]}/{idle["summary"]["handles"]["max"]}/{idle["summary"]["handles"]["end"]}.',
'- 서로 다른 입력 처리 뒤의 메모리 증가는 캐시/작업집합 변화와 일치할 수 있으나 본 관측만으로 내부 할당별 원인을 확정하지 않습니다. 유휴 상태의 지속 증가 여부를 별도 기록했습니다.','',
'## 실행 및 자료',
'- 실행: 설치 루트 Start_NovaBrain.bat. 중지: Stop_NovaBrain.bat (설치 PID·명령·cwd 검증). 접속: http://127.0.0.1:8000 및 /mobile. loopback만 유지, 방화벽/GPU/모델 변경 없음.',
f'- 최종 ready={summary["final_status"]["ready"]}, worker_pid={summary["final_status"]["worker_pid"]}. 서버와 모델을 실행 상태로 유지했습니다.',
'- 원시 자료: stability-validation.json, stability-summary.json, stability-soak.log, maintenance-pipeline.log, native-worker-recovery.json, memory-mappings.json, ui-validation.json, humaneval/run-manifest.json, humaneval/samples.jsonl, humaneval/results.json.',
'- 재실행 도구: stability_soak.py (생성/취소/의도적 워커 종료 포함), maintenance_pipeline.py, 기존 test_memory_guard.py 및 test_ui_headless.py. 평가 샘플을 삭제하거나 실패 샘플을 바꿔 재집계하지 마세요.']
(ROOT.parent/'STABILITY_HUMANEVAL_REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'summary':summary,'humaneval':{k:v for k,v in h.items() if k!='results'}},ensure_ascii=True,indent=2))
