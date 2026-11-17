"""VIONA-owned Chrome profile; DOM search input, no physical input or activation."""
import ctypes,json,re,subprocess,threading,time,urllib.request
import psutil
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,Error as BrowserError
from desktop_bridge import desktop

ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'data/chrome-search'
LOCK=threading.Lock()

def search_intent(text):
    return bool(re.search(r'찾아\s*줘|찾아\s*주세요|검색해\s*줘|검색해\s*주세요',text)) and not bool(re.search(r'검색하지|찾지\s*마|검색해\s*줘.{0,6}(?:입력하면|기능|만들)',text))

def clean_query(text):
    text=text.strip().strip('`"\'')
    text=re.sub(r'^(?:검색어|query)\s*[:：]\s*','',text,flags=re.I)
    return re.sub(r'\s+',' ',text).strip()[:180]

def endpoint():
    try:
        lines=(PROFILE/'DevToolsActivePort').read_text().splitlines();port=int(lines[0])
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=1) as r:data=json.load(r)
        if urlsplit(data['webSocketDebuggerUrl']).path!=lines[1]:return None
        return f'http://127.0.0.1:{port}'
    except (OSError,ValueError,KeyError,IndexError):return None

def ensure_chrome():
    address=endpoint()
    if address:return address
    chrome=next((p for p in (Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Google/Chrome/Application/chrome.exe')) if p.is_file()),None)
    if chrome is None:raise RuntimeError('Google Chrome이 설치되어 있지 않습니다.')
    PROFILE.mkdir(parents=True,exist_ok=True)
    foreground=ctypes.windll.user32.GetForegroundWindow()
    subprocess.Popen([str(chrome),'--no-startup-window','--no-first-run','--no-default-browser-check',
        '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+str(PROFILE)],
        creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        address=endpoint()
        if address:
            if ctypes.windll.user32.GetForegroundWindow()!=foreground:
                raise RuntimeError('Chrome 시작 중 포커스 변경이 감지되어 검색 조작을 중단했습니다.')
            return address
        time.sleep(.1)
    raise RuntimeError('전용 Chrome 연결 시간이 초과되었습니다.')

def run_search(query,cancel_event=None):
    query=clean_query(query)
    if not query:raise ValueError('무엇을 검색할지 알려주세요.')
    if not LOCK.acquire(blocking=False):raise RuntimeError('Chrome 검색을 진행 중입니다. 완료 후 다시 요청해 주세요.')
    try:
        def check_cancel():
            if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Chrome 검색을 중단했습니다.')
        check_cancel()
        if psutil.virtual_memory().available<2.5*2**30:raise RuntimeError('Chrome 검색을 시작할 RAM 여유가 부족합니다. 다른 작업 완료 후 다시 요청해 주세요.')
        with desktop.lock:
            error=desktop.activate()
            if error:raise RuntimeError(error['error']['message'])
        address=ensure_chrome()
        check_cancel()
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp(address)
            context=browser.contexts[0];cdp=browser.new_browser_cdp_session()
            # No activation: this window belongs only to VIONA, not the user's Chrome profile.
            foreground=ctypes.windll.user32.GetForegroundWindow()
            page=None;target=None
            try:previous=json.loads((PROFILE/'search-target.json').read_text())['targetId']
            except (OSError,ValueError,KeyError):previous=None
            for candidate in context.pages:
                session=context.new_cdp_session(candidate)
                info=session.send('Target.getTargetInfo')['targetInfo'];session.detach()
                if info['targetId']==previous:page=candidate;target={'targetId':previous};break
            if page is None:
                with context.expect_page(timeout=10000) as created:
                    target=cdp.send('Target.createTarget',{'url':'about:blank','newWindow':True,'background':True})
                page=created.value
                (PROFILE/'search-target.json').write_text(json.dumps(target),encoding='utf-8')
            if ctypes.windll.user32.GetForegroundWindow()!=foreground:
                raise RuntimeError('Chrome 창 생성 중 포커스 변경이 감지되어 검색을 중단했습니다.')
            page.goto('https://www.bing.com/',wait_until='domcontentloaded',timeout=30000)
            check_cancel()
            field=page.locator('#sb_form_q')
            field.fill(query,timeout=15000)
            if field.input_value()!=query:raise RuntimeError('검색창 입력 내용을 확인할 수 없습니다.')
            check_cancel()
            with page.expect_navigation(wait_until='domcontentloaded',timeout=30000):
                field.evaluate('(el) => el.form.requestSubmit()')
            try:page.locator('#b_results > li.b_algo h2 a').first.wait_for(state='attached',timeout=15000)
            except Exception:raise RuntimeError('검색 결과를 읽을 수 없습니다. Chrome에서 인증·연결 안내를 확인해 주세요.')
            items=page.locator('#b_results > li.b_algo')
            check_cancel()
            sources=[]
            for i in range(min(items.count(),8)):
                item=items.nth(i);link=item.locator('h2 a').first
                if not link.count():continue
                url=link.get_attribute('href') or '';host=urlsplit(url).hostname or ''
                if not url.startswith(('https://','http://')) or host in ('localhost','127.0.0.1','::1'):continue
                paragraph=item.locator('p').first
                sources.append({'title':link.inner_text()[:200],'url':url,'domain':host,'snippet':paragraph.inner_text()[:900] if paragraph.count() else ''})
                if len(sources)==5:break
            if not sources:raise RuntimeError('Chrome 검색 결과에서 읽을 수 있는 항목이 없습니다. 검색어를 바꿔 주세요.')
            return {'query':query,'sources':sources,'provider':'Chrome · Bing 화면','search_used':True,
                'window_title':page.title(),'result_url':page.url,'target_id':target['targetId'],
                'input_verified':True,'notice':'Chrome 검색 결과의 제목과 요약을 읽었습니다. 연결된 원문 전체를 검증한 것은 아닙니다.'}
    except BrowserError as exc:
        raise RuntimeError('Chrome 검색창을 조작하지 못했습니다. Chrome의 인증·연결 안내를 확인한 뒤 다시 요청해 주세요.') from exc
    finally:LOCK.release()
