import json,statistics,time,collections
from pathlib import Path
from validate_install import get
ROOT=Path(__file__).resolve().parent
r=json.loads((ROOT/'hybrid-validation.json').read_text(encoding='utf-8'))
assert r.get('passed') and r['elapsed_seconds']>=600
samples=r['samples'];gpu=[json.loads(x) for x in (ROOT/'hybrid-gpu-samples.jsonl').read_text(encoding='utf-8').splitlines()];gpu=[x['gpu'] for x in gpu if x.get('gpu',{}).get('available')]
summary={'duration':r['elapsed_seconds'],'requests':len(r['requests']),'events':r['events'],'resources':{}}
for group in ('server','worker'):
    summary['resources'][group]={}
    for field in ('rss','private','handles','cpu_machine_percent'):
        values=[s[group][field] for s in samples]
        summary['resources'][group][field]={'start':values[0],'peak':max(values),'end':values[-1],'mean':statistics.mean(values)}
metrics=[x['metrics'] for x in r['requests']]
summary.update({'tokens_per_second':sum(m['output_tokens'] for m in metrics)/sum(m['elapsed_seconds'] for m in metrics),
 'minimum_available_gib':min(s['available'] for s in samples)/2**30,
 'gpu':{'samples':len(gpu),'peak_used_mib':max(g['used_mib'] for g in gpu),'minimum_free_mib':min(g['free_mib'] for g in gpu),'mean_utilization':statistics.mean(g['utilization_percent'] for g in gpu),'peak_utilization':max(g['utilization_percent'] for g in gpu),'max_temperature':max(g['temperature_c'] for g in gpu)},
 'final_status':get('/status'),'final_gpu':get('/api/gpu')})
before=json.loads((ROOT/'random-words-before.json').read_text(encoding='utf-8'))
after=json.loads((ROOT/'random-words-after-reference.json').read_text(encoding='utf-8'))
counts=collections.Counter(c.get('context',{}).get('response_origin','model') for c in after['cases'])
summary['random_word_response_origins']=dict(counts)
(ROOT/'hybrid-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# NovaBrain CPU·GPU 분담 및 대화 응답 보완',f'작성: {time.strftime("%Y-%m-%dT%H:%M:%S%z")}','',
'## 실제 추론 배치',
'- Qwen2.5-Coder-1.5B-Instruct Q4_K_M 모델 파일은 그대로 유지했습니다. 기본 컨텍스트 8,192, CPU 최대 6스레드입니다.',
'- GPU: GTX 1060 3GB. CUDA llama-cpp-python 0.3.36 및 가상환경 안의 NVIDIA CUDA runtime 12.4.127, cuBLAS 12.4.5.8을 사용합니다. 시스템 PATH·드라이버·방화벽을 바꾸지 않았습니다.',
'- hybrid 모드는 GPU에 계산 블록 14개와 출력 레이어, CPU에 나머지 계산 블록 14개를 배치합니다. 이 버전의 n_gpu_layers=15는 출력 레이어를 포함합니다. 초기 14 설정이 실제로는 GPU 13블록+출력임을 로그에서 발견해 15로 보정했습니다.',
'- 실제 llama.cpp 로그: offloading 14 repeating layers, offloaded 15/29 layers. CPU KV 112MiB + CUDA KV 112MiB. 원문: hybrid-loader-evidence.log. 단순 UI 표시나 GPU 메모리 점유만으로 분담을 주장하지 않았습니다.',
'- 레이어는 의존 관계에 따라 CPU와 GPU를 오가며 처리합니다. 두 장치 사용률이 항상 같거나 속도가 두 배가 되는 방식은 아닙니다. hybrid 시작 시 VRAM 여유가 1,200MiB 미만이면 보호를 위해 CPU를 선택합니다.','',
'## 무작위 입력에서 실제 발견한 문제',
'- 고정 시드 20261114로 후보 20개에서 무작위 단어 8개 선택, 무의미 단어 1개, 문맥 전환/짧은 후속 질문 2개를 추가해 총 11개 입력을 검사했습니다.',
'- 원본 응답을 모두 보관했습니다. GPU만 입력했는데 영어로 고장 진단을 시작했고, 바나나의 색·종류를 잘못 설명했으며, 무의미한 단어를 실제 동물로 단정했습니다. 사과·비행기·후속 질문에서는 문장 반복도 확인했습니다.',
'- 첫 지침/샘플링 수정 뒤 반복은 줄었지만 일반 지식 오답이 남았습니다. v1 결과도 숨기거나 삭제하지 않았습니다(random-words-after-v1.json).','',
'## 수정한 응답 처리',
'- assistant_tools.py: 한국어 중심의 짧은 지침, 현재 질문 우선, 임의 진단/문맥 요약 방지. 단어만으로 사용자의 상황을 만들지 않도록 처리합니다.',
'- 검색 허용 상태의 짧은 단어는 한국어 위키백과의 실제 항목을 읽어 출처와 함께 짧게 인용합니다. 항목이 없거나 뜻이 불확실하면 구체적인 질문을 요청합니다. 모델이 생성한 설명처럼 표시하지 않고 response_origin=reference_excerpt 또는 clarification_router로 구분합니다.',
f'- 같은 11개 입력의 최종 처리: 출처 인용 {counts["reference_excerpt"]}개, 명확화 질문 {counts["clarification_router"]}개, 모델 생성 {counts["model"]}개. 이것은 모델 지능 점수나 11개 문제 정답률이 아닙니다.',
'- engine.py/worker.py: 향상 모드에 repeat_penalty=1.12, frequency_penalty=0.1 적용. 기존 enhance=False 생성의 기본값 1.0/0.0 유지. 이전 HumanEval 샘플이나 점수를 수정/재평가하지 않았습니다.',
'- Bing RSS의 일부 무관한 결과를 실제 발견했습니다. 검색 언어/시장 설정을 바꾸고 제목·요약·URL의 관련어 일치 필터를 추가했습니다. Python 공식 문서 검색은 python.org/docs.python.org 결과 3개, 항공 질문에서 근거가 부족한 결과는 제외했습니다. 이 필터도 의미적 관련성이나 진실을 보장하지 않으며 검색 누락이 가능합니다.',
'- UI는 다른 동시 작업의 구현을 보존하며 hybrid 선택지, 실제 블록 분담, GPU 사용률/VRAM 표시와 출처 카드의 저장·새로고침 복원을 보완했습니다. 사용자 실제 포인터·키보드 포커스·클립보드를 사용하지 않았습니다.','',
'## 검증',
f'- 실제 모델 반복 검사 {r["elapsed_seconds"]:.1f}초, 정상 완료 {len(r["requests"])}회, 별도 사용자 취소 2회·연결 종료 2회·런처 강제 종료 1회. 모든 기존 자식 회수 및 다음 요청 복구 성공.',
f'- 오류 {r["final_status"]["errors"]}회, 의도적 재시작 {r["final_status"]["restarts"]}회, 복구 {r["final_status"]["recoveries"]}회, 예상 밖 재시작 {r["final_status"]["restarts"]-5}회.',
f'- 출력 토큰/생성 시간 {summary["tokens_per_second"]:.2f} tokens/s. 반복 입력은 prefix cache의 이점이 있어 일반 질문 전체의 속도를 보장하지 않습니다. 최소 여유 RAM {summary["minimum_available_gib"]:.3f}GiB.',
f'- GPU 표본 {len(gpu)}개: 사용률 평균 {summary["gpu"]["mean_utilization"]:.1f}%, 최대 {summary["gpu"]["peak_utilization"]}%, 최대 사용 VRAM {summary["gpu"]["peak_used_mib"]}MiB, 최소 여유 {summary["gpu"]["minimum_free_mib"]}MiB, 최고 온도 {summary["gpu"]["max_temperature"]}°C. GPU 사용률은 디스플레이·다른 앱도 포함하므로 모델만의 사용률과 같지 않습니다.','',
'| 대상 | RSS 시작/최대/종료 GiB | Private 시작/최대/종료 GiB | 핸들 시작/최대/종료 | CPU 평균/최대(전체 CPU %) |',
'|---|---|---|---|---|']
for group in ('server','worker'):
    v=summary['resources'][group]
    fmt=lambda key,scale:'/ '.join(f'{v[key][k]/scale:.3f}' for k in ('start','peak','end'))
    lines.append(f'| {group} | {fmt("rss",2**30)} | {fmt("private",2**30)} | {fmt("handles",1)} | {v["cpu_machine_percent"]["mean"]:.2f}/{v["cpu_machine_percent"]["peak"]:.2f} |')
lines += ['',
'- 서버 자원은 포트 소유 프로세스와 모델 워커를 제외한 자식의 합계입니다. GPU 상태 조회용 nvidia-smi 자식도 일시적으로 포함되어 핸들/RSS 피크가 높아질 수 있으며 종료 값은 다시 감소했습니다. Private는 Windows private commit이고 USS와 같지 않습니다.',
'- 메모리/도구 회귀 테스트 24개 통과. 합성 RAM 보호, idle 표본, 실제 성장 감지, 자식 회수, tool token/외부 Origin 거부, 물리 입력 거부, 표시 커서 실패 시 중단, 출처 분리 등을 포함합니다.',
'- 별도 4개 문맥 검사에서 이름 기억, 주제 변경 후 산술, 영어 교정문장 후속 요청의 표면 검사 3개 통과. RAM/SSD 설명은 여전히 피상적이어서 완전 통과로 집계하지 않았습니다.',
'- 격리 headless Edge UI 검사 8개 통과: 이전 기록 이전·원본 유지, 대화 복수 보존, 출처 카드 새로고침 유지, JSON 내보내기, hybrid 선택, 테마, 모바일 표시. UI 스트림은 fixture로 검사했고 실제 모델/네트워크 검사는 별도 파일로 분리했습니다. JavaScript 오류 0개.',
'- 기존 13GiB 경고, 13.5GiB 새 생성 차단/보호 중단, 2GiB 여유 목표 및 워커 예열 후 누수 감지를 유지했습니다. 위험 RAM 실측 부하를 만들지 않았습니다.','',
'## 남은 한계',
'- 1.5B Coder 모델의 한국어 일반 지식과 후속 원인 설명은 여전히 약합니다. 웹 출처가 없는 긴 질문의 오답을 모두 해결하거나 GPT/Claude 수준의 지능을 만들었다고 주장하지 않습니다.',
'- 출처 인용과 명확화 처리는 모델 재학습이 아닙니다. 위키백과도 오류/최신성/동음이의 한계가 있으므로 중요한 내용은 원문과 공식 자료로 확인해야 합니다.',
'- 장시간 수 시간/수 일, 최대 32,768 컨텍스트, 물리 Safari, 모든 Windows 앱의 semantic 클릭/입력은 이번 검사 범위 밖입니다. 더 큰 모델로 자동 교체하지 않았습니다.','',
'## 파일 및 실행',
'- 변경: runtime_settings.py, runtime-settings.json, engine.py, worker.py, server.py, assistant_tools.py, ui.html, ui.js, test_memory_guard.py, test_assistant_tools.py. 기존 동시 작업 UI는 통째로 덮어쓰지 않았습니다.',
'- 변경 전 백업: ../backups/hybrid-20261114-183848/. 이전 GPU/인터페이스 백업: ../backups/assistant-ui-20261114-181030/.',
'- 근거: hybrid-validation.json, hybrid-gpu-samples.jsonl, hybrid-summary.json, hybrid-loader-evidence.log, hybrid-regression-tests.log, hybrid-ui-validation.json, random-words-before.json, random-words-after-v1.json, random-words-after-reference.json, conversation-focus-final.json, search-relevance-validation.json.',
f'- 최종 ready={summary["final_status"]["ready"]}, worker_pid={summary["final_status"]["worker_pid"]}, mode={summary["final_gpu"]["mode"]}. 로컬 서버를 실행 상태로 유지합니다.',
'- 접속: http://127.0.0.1:8000 및 /mobile. 설정 → 모델·장치 → CPU+GPU 분담. Start_NovaBrain.bat 실행, Stop_NovaBrain.bat 중지. loopback 외부 공개 없음.']
(ROOT.parent/'HYBRID_DIALOGUE_REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True,indent=2))
