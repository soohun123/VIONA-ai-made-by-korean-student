"""System-browser OAuth; loopback callbacks only, no tokens persisted or exposed to JS."""
import base64,ctypes,hmac,json,os,secrets,threading,time,urllib.parse,uuid,webbrowser
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path

PROVIDERS={
 'google':{'authorize':'https://accounts.google.com/o/oauth2/v2/auth','token':'https://oauth2.googleapis.com/token','userinfo':'https://openidconnect.googleapis.com/v1/userinfo','port':0},
 'naver':{'authorize':'https://nid.naver.com/oauth2.0/authorize','token':'https://nid.naver.com/oauth2.0/token','userinfo':'https://openapi.naver.com/v1/nid/me','port':43871}}


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect(data,decrypt=False):
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    function=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ctypes.WinError()
    try:return ctypes.string_at(target.data,target.size)
    finally:
        free=ctypes.windll.kernel32.LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p;free(target.data)


class Settings:
    def __init__(self,data):self.path=Path(data)/'accounts/oauth-settings.dat';self.lock=threading.RLock()
    def read(self):
        with self.lock:
            if not self.path.exists():return {}
            return json.loads(protect(self.path.read_bytes(),True).decode('utf-8'))
    def save(self,provider,client_id,secret):
        if provider not in PROVIDERS:raise ValueError('지원하지 않는 로그인 제공업체입니다.')
        client_id=str(client_id).strip();secret=str(secret).strip()
        if not client_id or len(client_id)>512 or len(secret)>1024:raise ValueError('Client ID와 Secret을 확인해 주세요.')
        if provider=='google' and not client_id.endswith('.apps.googleusercontent.com'):raise ValueError('Google 데스크톱 앱의 Client ID를 입력해 주세요.')
        with self.lock:
            data=self.read();previous=data.get(provider,{})
            if not secret:secret=previous.get('client_secret','')
            if not secret:raise ValueError('제공업체에서 발급한 Client Secret을 입력해 주세요.')
            data[provider]={'client_id':client_id,'client_secret':secret}
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(protect(json.dumps(data).encode('utf-8')));os.replace(tmp,self.path)
    def public(self):
        data=self.read()
        return {name:{'configured':bool(data.get(name,{}).get('client_id') and data.get(name,{}).get('client_secret')),
                      'client_id':data.get(name,{}).get('client_id','')} for name in PROVIDERS}


class SocialLogin:
    def __init__(self,settings,on_identity):
        self.settings=settings;self.on_identity=on_identity;self.lock=threading.RLock();self.pending=None;self.error=None
    def cancel(self):
        with self.lock:
            if self.pending:self.pending['cancel'].set()
            self.pending=None
    def status(self):
        with self.lock:return {'pending_provider':self.pending['provider'] if self.pending else None,'error':self.error}
    def start(self,provider):
        from authlib.integrations.requests_client import OAuth2Session
        if provider not in PROVIDERS:return {'error':'지원하지 않는 로그인 제공업체입니다.'}
        with self.lock:
            if self.pending:return {'error':'이미 로그인 중입니다. 완료하거나 취소해 주세요.'}
            config=self.settings.read().get(provider,{})
            if not config.get('client_id') or not config.get('client_secret'):
                return {'error':'서비스 로그인 설정이 아직 없습니다. 개발자 계정에서 제공업체 앱을 등록해 주세요.','code':'provider_not_configured'}
            definition=PROVIDERS[provider];state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
            callback={};done=threading.Event();cancel=threading.Event()
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    parsed=urllib.parse.urlsplit(self.path)
                    valid_host=self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
                    query=urllib.parse.parse_qs(parsed.query,keep_blank_values=True,max_num_fields=20) if len(self.path)<=8192 else {}
                    valid=valid_host and parsed.path==f'/oauth/callback/{provider}' and len(query.get('state',[]))==1 and hmac.compare_digest(query.get('state',[''])[0],state)
                    if not valid:self.send_error(400,'Invalid callback');return
                    if done.is_set():self.send_error(409);return
                    callback.update(query);done.set()
                    body='<!doctype html><meta charset="utf-8"><title>NOVERA 로그인</title><p>인증 응답을 받았습니다. NOVERA 앱으로 돌아가 결과를 확인하세요.</p>'.encode('utf-8')
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(body)
            try:server=HTTPServer(('127.0.0.1',definition['port']),Handler);server.timeout=.5
            except OSError:return {'error':'로그인 응답용 로컬 포트를 열 수 없습니다. 다른 로그인 작업을 마친 뒤 다시 시도하세요.'}
            redirect=f'http://127.0.0.1:{server.server_port}/oauth/callback/{provider}'
            client=OAuth2Session(config['client_id'],config['client_secret'],redirect_uri=redirect,state=state,
                    scope='openid email profile' if provider=='google' else None,token_endpoint_auth_method='client_secret_post',
                    code_challenge_method='S256' if provider=='google' else None)
            client.trust_env=False
            options={'code_verifier':verifier,'prompt':'select_account'} if provider=='google' else {}
            url,_=client.create_authorization_url(definition['authorize'],state=state,**options)
            pending={'provider':provider,'cancel':cancel};self.pending=pending;self.error=None
            def finish():
                try:
                    deadline=time.monotonic()+180
                    while not done.is_set() and not cancel.is_set() and time.monotonic()<deadline:server.handle_request()
                    if cancel.is_set():return
                    if not done.is_set():raise TimeoutError()
                    if callback.get('error') or len(callback.get('code',[]))!=1:raise ValueError('Provider declined')
                    kwargs={'code_verifier':verifier} if provider=='google' else {'state':state}
                    token=client.fetch_token(definition['token'],code=callback['code'][0],timeout=20,allow_redirects=False,**kwargs)
                    if not token.get('access_token') or str(token.get('token_type','')).lower()!='bearer':raise ValueError('Invalid access token')
                    response=client.get(definition['userinfo'],timeout=20,allow_redirects=False);response.raise_for_status();profile=response.json()
                    if provider=='naver':
                        if profile.get('resultcode')!='00':raise ValueError('Invalid provider response')
                        profile=profile.get('response',{})
                    if not isinstance(profile,dict):raise ValueError('Invalid profile')
                    with self.lock:
                        if self.pending is pending and not cancel.is_set():self.on_identity(provider,profile)
                except Exception:
                    with self.lock:
                        if self.pending is pending:self.error='로그인을 완료하지 못했습니다. 앱 등록·콜백 주소·제공업체 동의를 확인하고 다시 시도해 주세요.'
                finally:
                    server.server_close();client.close()
                    with self.lock:
                        if self.pending is pending:self.pending=None
            threading.Thread(target=finish,daemon=True).start()
            try:opened=webbrowser.open(url,new=2)
            except Exception:opened=False
            if not opened:self.cancel();return {'error':'기본 브라우저를 열지 못했습니다. 기본 브라우저 설정을 확인해 주세요.'}
            return {'ok':True,'notice':'기본 브라우저에서 로그인한 뒤 앱으로 돌아와 주세요.'}
