import json,hashlib,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
v=json.loads((ROOT/'validation-results.json').read_text(encoding='utf-8'))
u=json.loads((ROOT/'ui-validation.json').read_text(encoding='utf-8'))
h=json.loads((ROOT/'humaneval/results.json').read_text(encoding='utf-8'))
repo=json.loads((ROOT.parent/'setup/model-repository.json').read_text(encoding='utf-8-sig'))
s=v['summary'];cpu=u.get('cpu_summary',{})
rows='\n'.join(f"| {x['name']} | {'통과' if x['evaluation']['passed'] else '실패'} | {x['metrics']['tokens_per_second']:.2f} |" for x in v['tasks'])
report=f'''# NovaBrain v8 설치 및 실측 보고서

작성: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds')}

원본 ZIP을 찾아 설치했습니다. 원본 없이 재구성하지 않았습니다. D:\\NovaBrain은 Windows ACL로 생성이 거부되어 사용자의 승인으로 설치 위치를 변경했습니다.

## 설치 및 실행

- 설치 루트: `{ROOT.parent}`
- 애플리케이션: `{ROOT}`
- 원본: `D:\\수혀니당\\Documents\\NovaBrain_v8_retry.zip`
- 원본 백업: `backups/NovaBrain_v8_retry.original.zip` (기존 파일 삭제 없음)
- 실행: 루트의 `Start_NovaBrain.bat` → 브라우저에서 http://127.0.0.1:8000
- 중지: 루트의 `Stop_NovaBrain.bat` (이 설치의 PID·명령·작업 경로를 확인하고 자식 프로세스와 함께 종료)
- Python: 별도 설치한 CPython 3.11.9 x64, `Python311/`. 기존 3.12/3.15 유지, PATH 변경 없음.
- 가상환경: `NovaBrain_LLM_v8/.venv/`. 패키지 버전: `requirements.lock.txt`.
- PC/모바일 공통 서버. 현재는 `127.0.0.1:8000`만 수신하며 LAN·외부 공개·방화벽 변경 없음.
- PC 브라우저와 모바일 브라우저의 기록은 각 기기의 localStorage에 별도로 보관됩니다.

## 모델 및 설정

- 모델: Qwen2.5-Coder-1.5B-Instruct-GGUF / Q4_K_M
- 파일: `NovaBrain_LLM_v8/model.gguf`
- 크기: {(ROOT/'model.gguf').stat().st_size:,} bytes (약 {(ROOT/'model.gguf').stat().st_size/10**9:.2f} GB / {(ROOT/'model.gguf').stat().st_size/2**30:.3f} GiB)
- 공식 저장소: https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF
- 다운로드 고정 리비전: `{repo['sha']}`
- SHA-256: `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046` (저장소 LFS 값과 일치)
- GGUF v3, 339개 텐서, qwen2, file_type=15(Q4_K_M), 양자화 버전 2. 실제 llama.cpp 모델 로딩 완료.
- 메타데이터 `qwen2.context_length=32768`를 모델 할당 전에 확인합니다.
- 기본 컨텍스트 8,192, 설정 상한 32,768, 최대 응답 설정 16,384, CPU 추론/배치 각각 최대 6스레드, GPU 레이어 0.
- 32,768 설정은 기존 서버를 중지한 뒤 루트의 `Start_NovaBrain_32768.bat`로 실행합니다. 이 길이의 장문 품질·메모리 부하 테스트는 하지 않았습니다.
- 입력+응답이 컨텍스트 안에 들어가야 하므로 기본 8,192에서 응답 16,384를 요청하면 거부됩니다.
- 13 GiB에서 경고, 13.5 GiB에서 새 요청 차단/워커 중단. 여유 RAM 2.5 GiB 미만 또는 증가 추세 예측으로 더 일찍 중단할 수 있습니다. 최소 여유 목표는 2 GiB입니다.
- 보호/비정상 종료 후 안전한 RAM 상태의 다음 요청에서 워커를 다시 로드합니다. 폴링 방식이므로 다른 프로그램까지 포함한 시스템 RAM의 절대 상한은 보장하지 않습니다.

## 실제 Python 코딩 5문제 (첫 시도, 수정·재시도 없음)

| 문제 | 결과 | 토큰/초 |
|---|---|---:|
{rows}

- 정답: {s['passed']}/{s['total']} = {s['accuracy_percent']:.0f}% (자체 5문제이며 HumanEval 점수가 아님)
- 실패 원인: merge_intervals가 입력 리스트를 sort하고 내부 구간도 변경하여 '원본 변경 금지' 조건을 위반했습니다. 모델 출력은 수정하지 않았습니다.
- 평균 출력 속도: {s['mean_tokens_per_second']:.2f} tokens/s (각 요청의 입력 처리+출력 생성 시간 기준 평균)
- 총 출력 토큰/총 생성 시간: {s['weighted_tokens_per_second']:.2f} tokens/s
- 첫 출력 이후 평균 디코딩 속도: {s['mean_decode_tokens_per_second']:.2f} tokens/s
- 토큰 수는 출력 텍스트를 모델 토크나이저로 다시 센 값이며 EOS는 제외합니다.
- 테스트 중 시스템 사용 RAM 최대: {max(s['peak_system_used_gib'],s['status']['peak_system_used_gb']):.2f} GiB, 최소 여유: {s['minimum_available_gib']:.2f} GiB
- 모델 워커 트리 RSS 최대: {s['status']['peak_worker_gb']:.2f} GiB
- 시스템 전체 CPU 평균/최대: {s['mean_system_cpu_percent']:.1f}% / {s['peak_system_cpu_percent']:.1f}% (다른 앱 및 WASI 컴파일 포함)
- 별도 최종 UI 테스트의 워커 트리 CPU 평균/최대: {cpu.get('mean_worker_cpu_percent_of_machine',0):.1f}% / {cpu.get('peak_worker_cpu_percent_of_machine',0):.1f}% (전체 논리 CPU 용량 기준, 초기 로드·대기 포함)
- 5문제 테스트 구간 모델 운영 오류: {s['status']['errors']}회. 의도적 워커 강제 종료 1회, 다음 요청 복구 1회 성공.
- 최종 UI 테스트 구간: 사용자 중단 1회, 다음 요청 복구 1회 성공. 브라우저 JavaScript 오류 {len(u['errors'])}회.

## UI·스트리밍·메모리 검증

- 실제 한국어 응답: "{u['checks']['korean_reply']}"
- PC 화면 정상 표시를 헤드리스 Edge 렌더링과 스크린샷으로 확인.
- 스트리밍 중 DOM 변경 {u['checks']['dom_stream_mutations']}회 확인.
- 새로고침 후 대화 기록 유지, JSON 내보내기 확인.
- 모바일 공통 서버에서 실제 `add(a,b)` 코드 생성, 390×844 터치 화면에서 가로 넘침 없음.
- 실기기 iPhone Safari는 미검증. viewport-fit, safe-area, 16px 입력, 44px 터치 타깃 및 동적 뷰포트 대응 적용.
- `guard-validation.json`: 합성 메모리 측정값으로 13 경고, 13.5/13.9 중단, 32,768 초과 컨텍스트 거부 확인. 실제 RAM을 위험 임계값까지 소모하는 테스트는 하지 않았습니다.
- 모델 종료 시 Windows 가상환경 런처뿐 아니라 실제 Python 자식 프로세스도 종료하도록 보완.

## 발견한 오류와 수정

1. D: 루트 접근 거부 → 승인된 E: 경로 사용.
2. Python 3.11 없음 → Python Software Foundation의 서명이 Valid인 공식 설치기로 별도 설치.
3. 원본 engine.py 기본 컨텍스트 32,768 → 8,192로 변경, 모델 메타데이터 검사 후 할당, 최대 32,768 제한.
4. 이전 워커 출력이 새 워커 큐에 섞일 수 있는 구조 → 실행별 큐 분리.
5. 브라우저 생성 취소 후 동기 스트림이 정지하며 mutex가 남아 다음 요청이 409로 차단되는 문제 → 비동기 스트림 및 취소 시 워커 종료/잠금 해제. 수정 후 PC 취소→모바일 재생성 성공.
6. 생성 전용 메모리 감시 → 유휴 중 0.5초 주기 감시 추가, 샘플 보관/증가 추세 검사 보완.
7. temperature 0이 UI에서 기본값 0.7로 바뀌던 처리, 화면 링크 문구, 모바일 버튼 줄바꿈 수정.
8. 앱 내 브라우저 연결 실패 → 별도 헤드리스 Edge 테스트 사용. 사용자 포인터·키보드 포커스·클립보드 조작 없음.
9. 5문제 중 1개 모델 코드 오답은 측정 결과로 유지. 프로그램 오류 수정과 구분합니다.

## HumanEval 준비

- OpenAI 공식 HumanEval 데이터 164문제와 MIT LICENSE를 `humaneval/`에 보관했습니다. 원본 커밋은 `humaneval/revision.txt`.
- 데이터 SHA-256: `b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef`.
- `humaneval_offline.py` 및 루트 `Run_HumanEval_164.bat` 준비. 로컬 서버를 먼저 실행하고 다른 채팅 요청 없이 실행합니다.
- 문제당 단일 샘플, temperature=0, seed=42, max_tokens=1024. 저장된 샘플은 교체하지 않고 이어서 처리합니다. 마크다운 제거/들여쓰기 정규화만 적용, 로직 수정 없음.
- 실행 격리: Wasmtime 50.0.1의 WASI CPython 3.11.4. 네트워크 소켓 미제공, 호스트 환경변수 미상속, 표준 라이브러리만 읽기 전용 제공, 선형 메모리 256 MiB, 문제당 10초 제한.
- 소켓 차단·파일 쓰기 차단·비공개 호스트 경로 차단·무한 루프 타임아웃을 실제 확인했습니다. 생성 코드를 호스트 Python에서 exec하지 않습니다.
- 파이프라인 점검: HumanEval/0 단일 문제 {h['passed']}/{h['completed']} 통과. 이는 전체 점수가 아닙니다.
- **전체 164문제 pass@1은 미측정이며 목표 45~50% 달성을 주장하지 않습니다.** WASI 환경은 공식 네이티브 평가기와 런타임 차이가 있으므로 결과에 명시합니다.
- WASI Python 배포 출처: https://github.com/vmware-labs/webassembly-language-runtimes (배포 SHA-256도 확인함)

## 근거 파일

- `validation-results.json`: 5문제 프롬프트·원문 응답·코드·assert 결과·성능 원시 샘플
- `ui-validation.json`: 최종 UI/스트리밍/저장/취소/복구·CPU 측정
- `ui-validation.before-cancel-fix.json`: 취소 오류 발견 당시 기록
- `guard-validation.json`, `model-metadata.json`, `requirements.lock.txt`
- `desktop-verified.png`, `mobile-verified.png`
- `novabrain-health.log`, `server.stdout.log`, `server.stderr.log`
- `humaneval/samples.jsonl`, `humaneval/results.json`
'''
(ROOT.parent/'INSTALL_REPORT_KO.md').write_text(report,encoding='utf-8')
print(ROOT.parent/'INSTALL_REPORT_KO.md')
