import json, os, threading, math
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import psutil
from generation_resources import release_generation
from runtime_settings import read_settings

ROOT = Path(__file__).resolve().parent
MODEL = Path(os.getenv('NOVABRAIN_MODEL', str(ROOT / 'model.gguf')))
REQUESTED_CTX = int(os.getenv('NOVABRAIN_CTX', '8192'))
THREADS = min(6, max(1, int(os.getenv('NOVABRAIN_THREADS', str(read_settings()['cpu_threads'])))))
GPU_LAYERS = int(os.getenv('NOVABRAIN_GPU_LAYERS', '0'))
MIN_FREE_GB = float(os.getenv('NOVABRAIN_MIN_FREE_GB', '2.0'))
MAX_OUTPUT = 16384
app = FastAPI(title='NovaBrain LLM v3')
llm = None
load_error = None
gpu_fallback = None
effective_gpu_layers = 0
placement = None
text_adapter = None
last_input_proxy_tokens = None
model_limit = None
limit_source = 'unknown'
lock = threading.Lock()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[Message]
    max_tokens: int = Field(default=4096, ge=1, le=MAX_OUTPUT)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)
    repeat_penalty: float = Field(default=1.0,ge=1.0,le=1.3)
    frequency_penalty: float = Field(default=0.0,ge=0,le=0.5)
    code_only: bool = False

def memory():
    m = psutil.virtual_memory()
    return {'available_gb': round(m.available / 2**30, 2), 'total_gb': round(m.total / 2**30, 2)}

def gguf_limit(meta):
    # GGUF n_ctx_train reflects the architecture's trained context, not proof of extended context support.
    for k, v in meta.items():
        if k.endswith('.context_length'):
            try:
                n = int(v)
                if n > 0:
                    return n, k
            except (TypeError, ValueError):
                pass
    return None, 'GGUF context metadata missing'

@app.on_event('startup')
def startup():
    global llm, load_error, model_limit, limit_source,gpu_fallback,effective_gpu_layers,placement,text_adapter
    if not MODEL.is_file():
        load_error = f'모델 파일 없음: {MODEL}'
        return
    if not 512 <= REQUESTED_CTX <= 32768:
        load_error = 'NOVABRAIN_CTX는 512~32768 범위여야 합니다.'
        return
    # Conservative preflight; Windows available memory is checked again before generation.
    required = MODEL.stat().st_size / 2**30 * 1.25 + 1.5
    if memory()['available_gb'] < required + MIN_FREE_GB:
        load_error = f'메모리 부족 위험: 사용 가능 {memory()["available_gb"]}GB, 최소 예상 {required + MIN_FREE_GB:.1f}GB 필요. 다른 앱을 닫거나 작은 모델을 사용하세요.'
        return
    try:
        from gguf_metadata import read_metadata
        model_limit, limit_source = gguf_limit(read_metadata(MODEL))
        if model_limit is None or REQUESTED_CTX > model_limit:
            raise ValueError('컨텍스트가 GGUF 한계를 초과하거나 한계를 확인할 수 없습니다.')
        from cuda_runtime import initialize_cuda
        initialize_cuda()
        from llama_cpp import Llama,llama_supports_gpu_offload
        from text_adapter import resolve_adapter
        try:adapter_path,text_adapter=resolve_adapter(MODEL)
        except Exception as adapter_error:
            if os.getenv('NOVABRAIN_TEXT_LORA') not in (None,'off'):raise
            adapter_path=None;text_adapter={'error':str(adapter_error),'using_base':True}
        effective_gpu_layers=GPU_LAYERS if llama_supports_gpu_offload() else 0
        if GPU_LAYERS and not effective_gpu_layers:gpu_fallback='설치된 엔진이 GPU 오프로딩을 지원하지 않아 CPU를 사용합니다.'
        def load(layers):
            return Llama(model_path=str(MODEL), n_ctx=REQUESTED_CTX,
                         n_threads=THREADS,n_threads_batch=THREADS,n_gpu_layers=layers,
                         n_batch=128,n_ubatch=128,use_mmap=True,verbose=False,
                         lora_path=adapter_path,lora_scale=1.0)
        try:candidate=load(effective_gpu_layers)
        except Exception:
            if not effective_gpu_layers:raise
            effective_gpu_layers=0;gpu_fallback='GPU 로딩에 실패하여 CPU로 복구했습니다.'
            candidate=load(0)
        model_limit, limit_source = gguf_limit(candidate.metadata or {})
        if model_limit is None:
            load_error = 'GGUF 메타데이터에서 모델의 학습 컨텍스트 한계를 확인할 수 없습니다. 안전을 위해 실행하지 않습니다.'
            del candidate
            return
        if REQUESTED_CTX > model_limit:
            load_error = f'요청 컨텍스트 {REQUESTED_CTX:,}이 모델 메타데이터 한계 {model_limit:,}을 초과합니다. 확장 설정은 별도 검증이 필요합니다.'
            del candidate
            return
        llm = candidate
        blocks=next((int(v) for k,v in candidate.metadata.items() if k.endswith('.block_count')),0)
        gpu_blocks=blocks if effective_gpu_layers<0 else min(blocks,max(0,effective_gpu_layers-1))
        placement={'total_blocks':blocks,'cpu_blocks':blocks-gpu_blocks,'gpu_blocks':gpu_blocks,
                   'output_device':'GPU' if effective_gpu_layers else 'CPU',
                   'mode':'hybrid' if 0<gpu_blocks<blocks else 'gpu' if gpu_blocks else 'cpu'}
        load_error = None
    except Exception as exc:
        load_error = f'{type(exc).__name__}: {exc}'

@app.get('/')
def index():
    return FileResponse(ROOT / 'index.html')

@app.get('/status')
def status():
    return {'ready': llm is not None, 'model': MODEL.name,
            'context': REQUESTED_CTX, 'model_context_limit': model_limit,
            'limit_source': limit_source, 'max_output': MAX_OUTPUT,
            'threads': THREADS, 'gpu_layers': GPU_LAYERS,
            'memory': memory(), 'error': load_error,
            'note': '모델 메타데이터의 학습 한계만 검증. 실제 품질/성능은 별도 테스트 필요.'}

def prepare(req):
    global last_input_proxy_tokens
    if llm is None:
        raise HTTPException(503, load_error or '모델이 로드되지 않았습니다.')
    if memory()['available_gb'] < MIN_FREE_GB:
        raise HTTPException(503, f'사용 가능한 RAM이 {MIN_FREE_GB}GB 미만입니다. 다른 프로그램을 종료하세요.')
    messages = [dict(role=m.role, content=m.content) for m in req.messages
                if m.role in ('system', 'user', 'assistant') and m.content.strip()]
    if not messages or messages[-1]['role'] != 'user':
        raise HTTPException(400, '마지막 메시지는 user여야 합니다.')
    if messages[0]['role'] != 'system':
        messages.insert(0, {'role':'system','content':'당신의 이름은 VIONA입니다. 한국어로 정확하고 간결하게 답하세요.'})
    # llama-cpp-python chat formatting can add extra template tokens; reserve margin.
    reserve = max(256, math.ceil(REQUESTED_CTX * 0.03))
    budget = REQUESTED_CTX - req.max_tokens - reserve
    if budget < 128:
        raise HTTPException(422, f'응답 {req.max_tokens:,}토큰을 예약하면 입력 공간이 부족합니다. 응답 길이를 줄이세요.')
    system = messages[:1] if messages[0]['role'] == 'system' else []
    history = messages[len(system):]
    def count(ms):
        # Conservative proxy, NOT an exact chat-template token count.
        return len(llm.tokenize(json.dumps(ms, ensure_ascii=False).encode('utf-8'))) + 16 * len(ms)
    with lock:
        while len(history) > 1 and count(system + history) > budget:
            history.pop(0)
            while len(history)>1 and history[0]['role']!='user':history.pop(0)
        used = count(system + history)
    if used > budget:
        raise HTTPException(413, f'최근 입력이 너무 깁니다. 예상 입력 {used:,} / 허용 {budget:,}토큰. 메시지를 나누어 보내세요.')
    last_input_proxy_tokens=used
    return system + history

def error_text(exc):
    s = str(exc)
    if 'context' in s.lower() or 'token' in s.lower():
        return '모델의 실제 토큰 한도를 초과했습니다. 입력 또는 최대 응답 길이를 줄이세요. 상세: ' + s
    return s

@app.post('/chat')
def chat(req: ChatRequest):
    messages = prepare(req)
    with lock:
        try:
            result = llm.create_chat_completion(messages=messages, max_tokens=req.max_tokens,
                                                temperature=req.temperature, top_p=req.top_p)
        except Exception as exc:
            raise HTTPException(422, error_text(exc)) from exc
        finally:
            release_generation(llm)
    return {'reply': result['choices'][0]['message'].get('content') or '',
            'usage': result.get('usage', {})}

@app.post('/chat/stream')
def stream(req: ChatRequest):
    messages = prepare(req)
    def generate():
        if not lock.acquire(blocking=False):
            yield json.dumps({'error': '다른 응답을 생성 중입니다.'}, ensure_ascii=False) + '\n'
            return
        chunks = None
        try:
            chunks = llm.create_chat_completion(messages=messages, max_tokens=req.max_tokens,
                                                temperature=req.temperature, top_p=req.top_p,
                                                stream=True)
            for chunk in chunks:
                if memory()['available_gb'] < MIN_FREE_GB:
                    yield json.dumps({'error': '메모리 여유가 안전 기준 미만으로 감소하여 생성을 중단했습니다.'}, ensure_ascii=False) + '\n'
                    return
                delta = chunk['choices'][0].get('delta', {}).get('content') or ''
                if delta:
                    yield json.dumps({'token': delta}, ensure_ascii=False) + '\n'
            yield '{"done":true}\n'
        except Exception as exc:
            yield json.dumps({'error': error_text(exc)}, ensure_ascii=False) + '\n'
        finally:
            try:release_generation(llm,chunks)
            finally:lock.release()
    return StreamingResponse(generate(), media_type='application/x-ndjson',
                             headers={'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff'})
