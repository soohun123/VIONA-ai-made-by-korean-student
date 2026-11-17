"""Authenticated HTTPS tunnel gateway, isolated from local desktop/admin APIs."""
import hashlib,hmac,json,secrets,time,re
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import anyio,httpx
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,StreamingResponse,Response
from api_credentials import load_api_key
from model_catalog import seal

ROOT=Path(__file__).resolve().parent
SETTINGS=ROOT/'network-settings.json'
COOKIE='__Host-viona_session'
LIFETIME=7*24*3600

def network_settings():
    try:return json.loads(SETTINGS.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'public_url':'','cors_origins':[]}

class CurrentOriginCORS:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        origins=network_settings().get('cors_origins',[])
        middleware=CORSMiddleware(self.app,allow_origins=origins,allow_credentials=True,
            allow_methods=['GET','POST','OPTIONS'],allow_headers=['Authorization','Content-Type','X-NovaBrain-Token'],max_age=300)
        await middleware(scope,receive,send)

app=FastAPI(title='VIONA HTTPS gateway',docs_url=None,redoc_url=None,openapi_url=None)

def signature(stamp):return hmac.new(load_api_key().encode(),('viona-session:'+stamp).encode(),hashlib.sha256).hexdigest()
def authenticated(request):
    auth=request.headers.get('authorization','')
    if len(auth)<256 and auth.lower().startswith('bearer '):
        if secrets.compare_digest(auth[7:].encode(),load_api_key().encode()):return True
    try:
        stamp,mac=request.cookies.get(COOKIE,'').split('.',1)
        return 0<=time.time()-int(stamp)<LIFETIME and hmac.compare_digest(mac,signature(stamp))
    except (ValueError,TypeError):return False

LOGIN='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="dark light"><title>VIONA 로그인</title><link rel="stylesheet" href="/login.css"></head><body><main><div class="brand"><svg viewBox="0 0 40 40" aria-hidden="true"><path d="M4 5h7l9 21 9-21h7L20 38z" fill="currentColor"/></svg><h1>VIONA</h1></div><h2>나만의 작업 공간으로</h2><p>생각을 정리하고 새로운 가능성을 만나는 곳.<br>발급받은 API 키로 안전하게 시작하세요.</p><form method="post" action="/login"><label for="apiKey">VIONA API 키</label><input id="apiKey" name="key" type="password" autocomplete="current-password" required maxlength="128" placeholder="발급받은 고정 API 키 입력" aria-describedby="keyHelp"><p id="keyHelp" class="help">키는 이 브라우저의 대화 기록에 저장되지 않습니다.</p><button>작업 공간 열기 <span aria-hidden="true">→</span></button></form><footer>개인 AI · 암호화된 HTTPS 연결</footer></main></body></html>'''
CSS='''*{box-sizing:border-box}:root{color-scheme:dark;--bg:#121b17;--surface:#1b2921;--text:#f1f6f0;--muted:#b7c8b9;--line:#718574;--accent:#c1e5bd;--on:#16311e}body{margin:0;min-height:100vh;min-height:100dvh;display:grid;place-items:center;background:var(--bg);color:var(--text);font:16px/1.8 "Segoe UI","Malgun Gothic",system-ui,sans-serif;padding:28px}main{width:min(100%,480px);padding:44px;border:1px solid var(--line);border-radius:24px;background:var(--surface)}.brand{display:flex;align-items:center;gap:12px;margin-bottom:34px}.brand svg{width:30px;height:30px;color:var(--accent)}h1{font-size:24px;letter-spacing:1px;margin:0}.eyebrow{font-size:11px;letter-spacing:1.4px;color:var(--accent)}h2{font-size:28px;letter-spacing:-1px;line-height:1.5;margin:14px 0}p{color:var(--muted);font-size:14px;margin:0 0 26px;word-break:keep-all}form{margin-top:30px}label{display:block;font-size:14px;font-weight:600}input,button{width:100%;font:inherit;border-radius:12px;min-height:50px;padding:12px 16px}input{background:var(--bg);color:var(--text);border:1px solid var(--line);margin-top:10px}input::placeholder{color:var(--muted);font-size:14px}.help{font-size:12px;line-height:1.8;margin:10px 0 24px}button{display:flex;align-items:center;justify-content:space-between;background:var(--accent);color:var(--on);border:0;font-size:15px;font-weight:600;cursor:pointer;transition:filter .18s}button:hover{filter:brightness(1.08)}input:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:4px}footer{border-top:1px solid var(--line);padding-top:22px;margin-top:30px;color:var(--muted);font-size:12px;text-align:center}.error{color:#ffc2ae;border-left:2px solid currentColor;padding-left:12px;font-size:14px}@media(max-width:500px){body{padding:18px}main{padding:30px 24px;border-radius:20px}h2{font-size:26px}.brand{margin-bottom:28px}}@media(prefers-color-scheme:light){:root{color-scheme:light;--bg:#f5f7f2;--surface:#fff;--text:#17271c;--muted:#4c6250;--line:#7b8c77;--accent:#2d603d;--on:#fff}.error{color:#a9351c}}@media(prefers-reduced-motion:reduce){*{transition:none!important}}'''

@app.middleware('http')
async def boundary(request:Request,call_next):
    settings=network_settings();host=request.headers.get('host','').split(':')[0]
    permitted={'127.0.0.1','localhost',urlsplit(settings.get('public_url','')).hostname}
    if host not in permitted:return JSONResponse({'detail':'허용하지 않은 호스트입니다.'},status_code=403)
    origin=request.headers.get('origin')
    if origin and origin not in settings.get('cors_origins',[]):return JSONResponse({'detail':'허용하지 않은 Origin입니다.'},status_code=403)
    path=request.url.path
    if path not in ('/login','/login.css') and not authenticated(request):
        if path in ('/','/mobile'):response=HTMLResponse(LOGIN)
        else:response=JSONResponse({'detail':'VIONA API 키로 로그인해 주세요.'},status_code=401,headers={'WWW-Authenticate':'Bearer'})
    else:response=await call_next(request)
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin',
        'Strict-Transport-Security':'max-age=86400','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"})
    return response

@app.get('/login')
def login_page():return HTMLResponse(LOGIN)
@app.get('/login.css')
def login_css():return HTMLResponse(CSS,media_type='text/css')
@app.post('/login')
async def login(request:Request):
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>1024:return JSONResponse({'detail':'요청이 너무 큽니다.'},status_code=413)
    key=parse_qs(data.decode('utf-8',errors='replace')).get('key',[''])[0]
    if not secrets.compare_digest(key.encode(),load_api_key().encode()):
        await anyio.sleep(.5)
        return HTMLResponse(LOGIN.replace('<form method=', '<p class="error" role="alert">API 키가 올바르지 않습니다. 키를 확인하고 다시 입력해 주세요.</p><form method='),status_code=401)
    stamp=str(int(time.time()));response=RedirectResponse('/',status_code=303)
    response.set_cookie(COOKIE,stamp+'.'+signature(stamp),secure=True,httponly=True,samesite='strict',max_age=LIFETIME,path='/')
    return response

GET_ALLOWED={'/','/mobile','/app.js','/app.css','/models-ui.js','/media-ui.js','/status','/api/gpu','/api/v1/status','/api/capabilities','/api/content-filter','/api/models','/api/media'}
POST_ALLOWED={'/chat/stream','/api/v1/chat/stream','/admin/cancel','/api/media/upload','/api/media/jobs'}

@app.get('/public-ui.js')
def public_ui():
    code="""(()=>{for(const id of ['openDesktop','desktopShortcut','settingsDesktop','applyGpu']){const el=document.getElementById(id);if(el){el.disabled=true;el.hidden=true;}}const gpu=document.getElementById('gpuMode');if(gpu)gpu.disabled=true;const info=document.getElementById('composerHint');if(info)info.textContent='보안 HTTPS 연결 · PC 도구는 로컬 주소에서 사용';})();"""
    return Response(code,media_type='application/javascript')

@app.api_route('/{path:path}',methods=['GET','POST','PATCH','DELETE','PUT'])
async def proxy(request:Request,path:str):
    target='/'+path
    dynamic_get=bool(re.fullmatch(r'/(?:api/media/jobs/[a-f0-9]{32}|media/[a-f0-9]{32}\.png|published-ui/[a-f0-9]{32}/(?:ui\.js|app\.css|media-ui\.js|models-ui\.js))',target))
    dynamic_post=bool(re.fullmatch(r'/api/media/jobs/[a-f0-9]{32}/cancel',target))
    if (request.method=='GET' and target not in GET_ALLOWED and not dynamic_get) or (request.method=='POST' and target not in POST_ALLOWED and not dynamic_post) or request.method not in ('GET','POST'):
        return JSONResponse({'detail':'이 기능은 PC의 로컬 주소에서만 사용할 수 있습니다.'},status_code=403)
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>(14200000 if target=='/api/media/upload' else 512*1024):return JSONResponse({'detail':'요청이 너무 큽니다.'},status_code=413)
    if request.method=='POST' and target.endswith('/chat/stream'):
        try:
            payload=json.loads(data)
            payload.update({'plugin_id':'','desktop_context':''})
            payload.setdefault('messages',[])
            payload['messages']=[m for m in payload['messages'] if isinstance(m,dict)]
            payload['messages'].insert(0,{'role':'system','content':'당신의 이름은 VIONA입니다. 한국어로 정확하고 간결하게 답하세요.'})
            data=json.dumps(payload,ensure_ascii=False).encode()
        except (ValueError,TypeError,KeyError):return JSONResponse({'detail':'잘못된 채팅 요청입니다.'},status_code=422)
    headers={'Content-Type':request.headers.get('content-type','application/json'),'Accept-Encoding':'identity','X-Viona-Public':seal()}
    if target.startswith('/api/v1/'):headers['Authorization']='Bearer '+load_api_key()
    client=httpx.AsyncClient(timeout=httpx.Timeout(15,read=600),trust_env=False)
    try:
        upstream=await client.send(client.build_request(request.method,'http://127.0.0.1:8000'+target,content=bytes(data),headers=headers),stream=True)
    except httpx.HTTPError:
        await client.aclose();return JSONResponse({'detail':'로컬 VIONA 서버를 연결하는 중입니다.'},status_code=503)
    if target=='/api/capabilities':
        body=json.loads(await upstream.aread());await upstream.aclose();await client.aclose()
        body.update({'tool_token':'','desktop_available':False,'desktop_policy':'로컬 PC에서만 사용 가능','public_gateway':True})
        return JSONResponse(body)
    if target in ('/','/mobile'):
        html=(await upstream.aread()).decode('utf-8');status=upstream.status_code
        await upstream.aclose();await client.aclose()
        for script in ('plugin-ui.js','training-ui.js'):
            html=html.replace('<script src="/'+script+'"></script>','')
        html=html.replace('</body>','<script src="/public-ui.js"></script></body>')
        return HTMLResponse(html,status_code=status)
    async def body_stream():
        try:
            async for chunk in upstream.aiter_raw():yield chunk
        finally:
            with anyio.CancelScope(shield=True):
                await upstream.aclose();await client.aclose()
    return StreamingResponse(body_stream(),status_code=upstream.status_code,media_type=upstream.headers.get('content-type','application/octet-stream'))

app.add_middleware(CurrentOriginCORS)
