"""Build an evidence-linked Korean report from completed local validation artifacts."""
import json,statistics,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
soak=read('media-hybrid-stability-validation.json');assert soak.get('passed'),soak.get('fatal_error')
samples=soak['samples'];G=2**30
def triplet(values,divisor=1):return '/'.join(f'{x/divisor:.3f}' for x in (values[0],max(values),values[-1]))
rows=[]
for key,label in [('server','서버'),('worker','워커 트리')]:
    group=[s[key] for s in samples]
    cpu=[s['cpu_machine_percent'] for s in group]
    rows.append('|'+label+'|'+triplet([s['rss'] for s in group],G)+'|'+triplet([s['private'] for s in group],G)+'|'+triplet([s['handles'] for s in group])+'|'+f'{statistics.mean(cpu):.2f}/{max(cpu):.2f}'+'|'+triplet([len(s['pids']) for s in group])+'|')
finalpid=samples[-1]['worker_pid'];same=[s for s in samples if s['worker_pid']==finalpid and s['ready']]
warm=[s for s in same if s['time']>=same[0]['time']+30];a,b=warm[0]['worker'],warm[-1]['worker']
metrics=[r['metrics'] for r in soak['requests']]
speed=sum(m['output_tokens'] for m in metrics)/sum(m['elapsed_seconds'] for m in metrics)
gpu=read('media-soak-gpu-samples.json');validgpu=[s for s in gpu if s.get('available')]
gen=read('local-media-generate-validation.json')['job'];vision=read('local-media-read-validation.json')['job'];cancel=read('local-media-cancel-validation.json')
initial=soak['initial_status'];final=soak['final_status'];delta=final['restarts']-initial['restarts']
summary={'elapsed_seconds':soak['elapsed_seconds'],'completed_requests':len(soak['requests']),'errors':final['errors']-initial['errors'],'restart_delta':delta,'recovery_delta':final['recoveries']-initial['recoveries'],'weighted_tokens_per_second':speed,'maximum_used_gib':max(s['used'] for s in samples)/G,'minimum_available_gib':min(s['available'] for s in samples)/G,'same_final_worker_rss_delta_mib':(b['rss']-a['rss'])/2**20,'same_final_worker_private_delta_mib':(b['private']-a['private'])/2**20,'gpu_samples':len(validgpu)}
(ROOT/'local-media-final-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
report=f'''# NovaBrain 로컬 이미지·CPU/GPU 배치 통합 검증
작성: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}

## 변경과 사용법
- PC http://127.0.0.1:8000 / 모바일 http://127.0.0.1:8000/mobile 의 `이미지`에서 이미지 읽기·생성, 작업 중단, 결과 다운로드를 사용할 수 있습니다. 이미지와 답변은 대화 기록에 보존합니다. 파일은 PNG/JPEG/WebP, 최대 10MB 및 1,600만 픽셀, 로컬 정규화 PNG는 긴 변 1280 이하입니다.
- 승인받은 공개 모델 다운로드 외에 이미지 처리용 외부 API는 사용하지 않습니다. 원본 이미지 업로드·분석·생성·선택적 한국어 번역은 이 PC에서 처리합니다. 별도 웹 검색 기능의 외부 검색 동작은 이전 설정대로입니다.
- GTX 1060 3GB에서 이미지 작업 전에 대화 워커를 내리고, 이미지 프로세스 종료·회수 후 대화 워커를 복구합니다. 이미지 작업과 대화 생성을 직렬화합니다. CUDA 생성 실패 시 CPU 경로를 시도합니다.
- 생성 크기 256/384/512, 4~24 steps(API), 화면 선택 8/12/20 steps, 고정 seed 42를 제공합니다. CUDA 이미지 생성은 diffusion GPU / text encoder·VAE CPU, VRAM 예산 1.5GiB입니다.
- 컴퓨터 유즈는 불필요한 모델 안내문 없이 도구를 열며 완료 결과만 짧게 표시합니다. 대상 요소를 선택한 후 semantic 실행 버튼으로 조작합니다. 자유로운 자연어를 자율 실행하는 범용 데스크톱 에이전트는 아직 구현하지 않았습니다. 실제 포인터·포커스·클립보드는 사용하지 않습니다. 표시 커서는 두 번째 실제 Windows 마우스 장치가 아닙니다.
- 기존 economy 지침·문맥 축약·코드 전용 조기 종료를 유지합니다. 이미지 자체는 대화 텍스트로 매번 재전송하지 않고 로컬 이미지 ID로 저장합니다. 필요한 이미지 분석과 번역만 호출합니다.

## 속도 배치
- 공개 GGUF의 28개 transformer block 구조를 확인해 GPU 14/20/24/26개 배치를 동일 질문 두 개로 실측했습니다. 평균 출력/전체 생성시간 29.82 → 45.95 → 50.51 → 52.63 tokens/s. 선택값 CPU 2 / GPU 26 block, 출력층 GPU(n_gpu_layers=27)입니다.
- 이는 두 질문에 대한 배치 비교이며 모든 입력에서 76.5% 빨라진다는 보장은 아닙니다. 뉴런 재배열·학습으로 얻은 새 모델은 아닙니다. 여유 VRAM에 따라 설정이 낮아질 수 있습니다. 원시 결과: NovaBrain_LLM_v8/placement-tuning.json.
- 최신 native 로딩 로그: `offloading 26 repeating layers`, `offloaded 27/29 layers`, CPU KV 16MiB / CUDA KV 208MiB. 별도 실제 계산 `19+23` → `42`. selected-placement-native-evidence.log에 보존했습니다.

## 실제 이미지 결과
- 도형 fixture 읽기: {vision['elapsed_seconds']:.2f}초(모델 전환·복구 포함), 빨간 사각형과 파란 원 식별. 별도 PC UI 실제 읽기 및 한국어 변환 시험 완료.
- 실제 CUDA 이미지 생성: 384×384, 12 steps, seed 42, {gen['elapsed_seconds']:.2f}초(전환·복구 포함). 빨간 로봇 PNG 생성 성공. 책·흰 배경 요청은 미반영했으므로 프롬프트 완전 준수라고 평가하지 않습니다.
- 해당 생성 중 시스템 RAM 최대 {gen['peak_system_used_gib']:.3f}GiB, 최소 여유 {gen['minimum_available_gib']:.3f}GiB. 읽기 최대 {vision['peak_system_used_gib']:.3f}GiB / 최소 여유 {vision['minimum_available_gib']:.3f}GiB.
- 별도 실제 512×512/20 steps 생성 중 취소: {cancel['job']['elapsed_seconds']:.2f}초 후 취소·복구 완료, native PIDs {cancel['native_pids']} 생존 0. 뒤이은 실제 대화 `19+23` → `42` 확인.
- 읽기 모델과 한국어 번역은 환각·어색한 표현이 생길 수 있습니다. 원문 설명도 펼쳐 볼 수 있습니다. OCR·정밀 도표·의료 영상·이미지 편집 품질은 검증하지 않았습니다. CPU 자동 대체 경로는 합성 실패 테스트를 했으며 이번 실제 생성은 CUDA였습니다.

## 추가 발견: 요청 샘플러 메모리 수거 지연
+- 수정 전 별도 607초/74회 시험에서 예열 후 동일 워커 private +73.19MiB, RSS +73.41MiB를 관측했습니다. 중간에 감소한 뒤에도 재차 증가했습니다. 이 원시 결과는 media-hybrid-stability-before-sampler-fix.json에 보존했습니다.
+- 설치된 llama-cpp-python 0.3.36에서 generate가 self._sampler를 교체(llama.py:896)하고, LlamaSampler의 ExitStack free_sampler 콜백은 self를 참조(_internals.py:684~692)하여 Python 순환 GC까지 native sampler 해제가 지연됩니다. 요청마다 교체되는 이 객체는 정상적인 모델 mmap/KV 캐시와 별개입니다.
+- generation_resources.py가 완료·오류·조기 종료 시 스트림과 요청 sampler.close()를 명시적으로 호출하고 참조를 비웁니다. worker.py와 engine.py 양쪽 경로에 적용했습니다. 모델·컨텍스트·KV 캐시 자체를 매번 해제하거나 누수 감지를 제거하지 않았습니다. 내부 API는 고정된 0.3.36 소스로 확인했으며 엔진 버전 변경 시 재검증이 필요합니다.
+- 아래 수치는 sampler 수정 후 다시 수행한 10분 시험입니다. 수정 전·후 시험을 합쳐 한 시험이라고 집계하지 않았습니다.

## 최종 배치의 10분 실제 시험
- {soak['elapsed_seconds']:.1f}초, 완료 생성 {len(soak['requests'])}회. 별도 사용자 취소 2회, 연결 종료 2회, 전용 워커 런처 종료 1회. 이전 프로세스 잔류 0, 모두 다음 생성 복구 성공.
- 오류 증가 {summary['errors']}회. 재시작 증가 {delta}회 / 복구 증가 {summary['recovery_delta']}회는 위 의도적 중단 5회에 대응합니다. 완료 출력/생성시간 가중 속도 {speed:.2f} tokens/s.
- 시스템 사용 최대 {summary['maximum_used_gib']:.3f}GiB, 최소 여유 {summary['minimum_available_gib']:.3f}GiB. RAM을 위험 한도까지 소비하지 않았습니다. 13GiB 경고·13.5GiB 차단 및 중단·2GiB 여유 목표, 기존 30초 예열 제외·120초간 1GiB 증가 감지를 유지합니다. 이미지 작업은 시작 시 3GiB 여유를 요구하고 실행 중 2.5GiB 미만에서 보호 중단합니다.

| 대상 | RSS 시작/최대/종료 GiB | Private 시작/최대/종료 GiB | 핸들 시작/최대/종료 | CPU 평균/최대 % | 프로세스 시작/최대/종료 |
|---|---|---|---|---|---|
{chr(10).join(rows)}

- 서버는 실제 포트 소유 Python PID, 워커는 전용 venv 런처·실제 Python·conhost 트리 합계입니다. CPU는 전체 논리 CPU 용량 대비 백분율, private는 Windows private commit으로 USS가 아닙니다. RSS 합산에는 공유 페이지가 중복될 수 있습니다.
- 최종 동일 워커 예열 후 RSS 변화 {summary['same_final_worker_rss_delta_mib']:.2f}MiB / private 변화 {summary['same_final_worker_private_delta_mib']:.2f}MiB / 핸들 {a['handles']}→{b['handles']}. model.gguf mmap RSS 1,117,323,264 bytes를 별도 기록했습니다. 모델 로딩·KV 캐시·mmap 상주와 종료 후 남는 프로세스를 구분했습니다. 이 구간에서 지속 누수 증거는 없으며 장시간·최대 컨텍스트 누수 부재를 증명하지는 않습니다.
- GPU 관측은 시험 도중 시작한 {len(validgpu)}표본입니다. GPU 사용률 최대 {max(s['utilization_percent'] for s in validgpu)}%, 사용 VRAM 최대 {max(s['used_mib'] for s in validgpu)}MiB. 전체 시험 내내 측정한 GPU trace는 아닙니다. GPU 사용률에는 디스플레이와 다른 앱 사용량도 포함됩니다.

## 회귀·화면·평가
- 단위 회귀 54개 통과: 합성 RAM 한도, 업로드 크기/형식/경로/메타데이터, 죽은 부모 자식 회수, 취소된 번역 워커 정리, 이미지 실패 후 복구, 복구 실패 오류 표시, 권한 검사, 조용한 컴퓨터 유즈 경로 포함.
- headless Edge 실제 이미지 읽기, 기록 유지, 생성 이미지 재개, PC/390px 모바일 도구·가로 넘침, 기본 UI 및 플러그인 CRUD 회귀 통과. 브라우저 오류 0. 사용자 브라우저 프로필·포인터·키보드 포커스를 사용하지 않았습니다. 물리 휴대폰/Safari는 미검증입니다.
- 최신 코드 전용 조기 종료 후 요청 샘플러 정리, 생성한 add 함수의 WASI 격리 실행, 뒤이은 별도 질문 응답도 통과했습니다(sampler-code-only-validation.json). 생성 코드는 호스트 Python에서 실행하지 않았습니다.
- 이번 추가 모델은 HumanEval 대상이 아닙니다. 기존 Qwen CPU 평가 164/164, 31/164=18.90% pass@1 원시 자료를 보존했습니다. 새 GPU 배치·지침으로 164문제를 다시 생성하지 않았으므로 이전 점수를 현재 설정의 재평가 결과라고 주장하지 않습니다. 기존 WASI 격리·네트워크 차단·자원 제한을 유지합니다.

## 수정·자료·실행
- 수정: server.py(미디어 API·취소 번역 정리), worker.py/engine.py(요청 샘플러 명시 해제), runtime_settings.py/runtime-settings.json(분담 조정), assistant_tools.py/plugin_registry.py(조용한 도구 연결·이미지 권한), ui.html/ui.js/plugin-ui.js/app.css(공통 화면), requirements.txt/requirements.lock.txt(Pillow).
- 신규: generation_resources.py, media_jobs.py(직렬 작업·RAM 보호·프로세스 회수·복구), vision_worker.py(로컬 Moondream), media-ui.js, install_media_assets.py, 검증 스크립트. 복구 실패를 성공으로 숨기지 않으며 이미지 결과가 이미 있으면 다운로드는 유지합니다. 한국어 번역 실패 시 원문을 남깁니다.
- 수정 전 백업: backups/media-20261114-210348. 기존 파일·사용자 이미지·대화 기록은 삭제하지 않았습니다. data/media/images 및 jobs는 결과·진단을 보존하므로 사용량에 따라 디스크를 차지합니다.
- 원시 자료: NovaBrain_LLM_v8/local-media-*-validation.json, media-*-validation.json, media-hybrid-stability-validation.json, media-soak-gpu-samples.json, media-model-memory-maps.json, media-assets-manifest.json. 이미지 생성 결과: NovaBrain_LLM_v8/data/media/images/{gen['id']}.png.
- 실행: NovaBrain_LLM_v8/start_local.bat. 중지: stop_local.bat(기록 PID·명령·설치 경로를 확인하는 stop_local.py). 서버는 127.0.0.1:8000으로 유지하며 LAN·방화벽은 변경하지 않았습니다.

- 최종 실행 상태: local-media-final-state.json의 ready=true, errors=0, active_job=null, 잔류 미디어 프로세스 0을 확인했습니다. PC·모바일은 같은 정상 대화 워커를 사용합니다.

## 공개 자산 출처
- 읽기: [Moondream2 ggml-org projector](https://huggingface.co/ggml-org/moondream2-20250414-GGUF), [community Q4_K_M text quant](https://huggingface.co/corono1/moondream2-2b-q4_k_m-gguf). Qwen 대화 모델과 별도로 교대 로딩합니다.
- 생성: [GPUStack Stable Diffusion 1.5 Q4_0](https://huggingface.co/gpustack/stable-diffusion-v1-5-GGUF), [stable-diffusion.cpp 공식 release master-1098-b521db4](https://github.com/leejet/stable-diffusion.cpp/releases/tag/master-1098-b521db4). 각 고정 revision·파일 크기·SHA-256 검증 결과는 manifest에 보존했습니다.
'''
(ROOT.parent/'LOCAL_MEDIA_SPEED_REPORT_KO.md').write_text(report,encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True,indent=2))
