import datetime,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
v=json.loads((ROOT/'memory-fix-validation.json').read_text(encoding='utf-8'))
assert 'error' not in v
s=v['summary']
report=f'''# NovaBrain 메모리 경고 수정

작성: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds')}

실제 로그에서 17:17:08 및 17:20:05의 "워커 메모리 지속 증가: 누수 의심" 종료를 확인했습니다. 두 번째는 로드 완료 직후 0.5초 이내에 발생했습니다.

원인은 감시기가 모델이 없는 대기 시간의 RSS=0 샘플을 저장하고, 모델 로딩 후 정상 RSS 약 1.86 GiB와 비교한 것입니다. 비교 시점이 120초 이상이고 증가가 1 GiB를 넘으면 누수로 처리했습니다. stop에서 샘플을 지워도 대기 중 다시 0 샘플이 쌓여 다음 로딩까지 반복됐습니다.

## 수정

- 수정 전 server.py와 건강 로그를 `backups/`에 타임스탬프를 붙여 보관했습니다.
- 워커가 없거나 준비되지 않았을 때는 RSS 비교 샘플을 축적하지 않습니다.
- 로딩 시작과 완료 때 기준을 초기화하여 워커별 표본을 분리합니다.
- 로드 후 30초 예열 구간의 RSS는 누수 추정에서 제외합니다. 예열 이후 같은 워커에서 최소 120초 간격으로 1 GiB 초과 증가하면 기존 보호 중단이 적용됩니다.
- 13 GiB 경고, 13.5 GiB 중단, 최소 RAM 여유 및 워커 RSS 상한은 예열 중에도 유지합니다.
- stdout/stderr 리더가 끝나면 파이프를 닫고, 워커 중단 시 stdin도 닫도록 보완했습니다.
- 사용자 파일·대화 기록·모델은 삭제하지 않았습니다. 이 설치의 서버만 재시작했으며 LAN 공개는 하지 않았습니다.

## 검증

- `memory-fix-reproduction.json`: 이전 코드에 대기 RSS=0, 로딩 후 1.86 GiB, 시스템 RAM 안정 10 GiB를 주면 동일한 누수 경고가 발생함을 재현했습니다.
- `test_memory_guard.py`: 8개 회귀 테스트 통과. 대기 표본 제외, 로딩 기준 초기화, 예열 제외, 안정 모델 유지, 실제 증가 감지, 예열 중 절대 RSS 제한, 시스템 RAM 제한, 파이프 종료를 확인했습니다.
- `check_guards.py`: 13 GiB 경고 및 13.5/13.9 GiB 중단, 최대 컨텍스트 초과 거부를 재확인했습니다. 실제 RAM을 위험 임계값까지 소모하지 않았습니다.
- 실제 GGUF 모델 연속 요청 8회 후 {s['idle_monitor_seconds']}초 동안 매초 감시하고 마지막 응답까지 총 {s['completed_requests']}회 완료했습니다.
- 감시 중 동일 워커 PID 유지: {s['worker_pid_unchanged']}, 예상치 못한 재시작: {s['restarts']}회.
- 대기 감시 시작/종료 워커 RSS: {s['rss_at_idle_start_gib']:.3f} / {s['rss_at_idle_end_gib']:.3f} GiB.
- 최대 워커 RSS: {s['maximum_worker_rss_gib']:.3f} GiB. 최소 시스템 여유 RAM: {s['minimum_available_gib']:.2f} GiB.
- 최종 ready={s['final_status']['ready']}, error={s['final_status']['error']}. 로컬 서버를 실행 상태로 유지했습니다.

이번 로그의 누수 판정 오류를 재현하고 수정했습니다. 이 검사는 수 시간·수 일 사용의 모든 메모리 누수 부재를 증명하는 장기 검사는 아닙니다.

원시 결과: `NovaBrain_LLM_v8/memory-fix-validation.json` 및 `memory-fix-reproduction.json`.
수정 파일: `NovaBrain_LLM_v8/server.py`.
접속: http://127.0.0.1:8000
'''
(ROOT.parent/'MEMORY_FIX_REPORT_KO.md').write_text(report,encoding='utf-8')
print(report)
