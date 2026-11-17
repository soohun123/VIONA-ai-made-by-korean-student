import json,time,threading,statistics
from pathlib import Path
import psutil
from playwright.sync_api import sync_playwright
from validate_install import get
ROOT=Path(__file__).resolve().parent
result={'browser':'Microsoft Edge headless; isolated test context','checks':{},'errors':[]}
samples=[];stop=threading.Event();workers={}
def monitor():
    while not stop.wait(.25):
        try:
            status=get('/status');pid=status.get('worker_pid')
            if pid:
                processes=[psutil.Process(pid)]+psutil.Process(pid).children(recursive=True)
                cpu=0;rss=0
                for proc in processes:
                    if proc.pid not in workers:workers[proc.pid]=proc;proc.cpu_percent(None)
                    cpu+=workers[proc.pid].cpu_percent(None)/psutil.cpu_count()
                    rss+=proc.memory_info().rss/2**30
                samples.append({'worker_cpu_percent_of_machine':cpu,'worker_rss_gib':rss})
        except Exception:pass
threading.Thread(target=monitor,daemon=True).start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1280,'height':900})
        page=context.new_page();page.on('pageerror',lambda e:result['errors'].append(str(e)))
        page.goto('http://127.0.0.1:8000',wait_until='networkidle')
        result['checks']['desktop_title']=page.title()
        page.locator('summary').click();page.locator('#maxTokens').fill('128')
        page.evaluate("window.novaChanges=0; new MutationObserver(()=>window.novaChanges++).observe(document.querySelector('#log'),{subtree:true,childList:true,characterData:true})")
        page.locator('#prompt').fill('안녕하세요. 파이썬에서 리스트는 무엇인지 한국어 한 문장으로 설명해 주세요.')
        page.locator('#send').click()
        page.wait_for_function("document.querySelector('#send').disabled === false",timeout=120000)
        reply=page.locator('.msg.assistant .body').last.inner_text()
        assert reply and '오류:' not in reply
        result['checks']['korean_reply']=reply
        result['checks']['dom_stream_mutations']=page.evaluate('window.novaChanges')
        assert result['checks']['dom_stream_mutations']>2
        page.screenshot(path=str(ROOT/'desktop-verified.png'),full_page=True)
        page.reload(wait_until='networkidle')
        assert page.locator('.msg.assistant .body').last.inner_text()==reply
        result['checks']['history_survives_reload']=True
        with page.expect_download() as download:
            page.locator('#export').click()
        path=ROOT/'ui-chat-export.json';download.value.save_as(str(path))
        assert len(json.loads(path.read_text(encoding='utf-8')))>=2
        result['checks']['history_export']=True
        page.locator('summary').click();page.locator('#maxTokens').fill('1024')
        page.locator('#prompt').fill('파이썬 정렬 알고리즘 10개를 코드와 함께 아주 길게 설명해 줘.')
        page.locator('#send').click()
        page.wait_for_function("document.querySelectorAll('.msg.assistant .body').length===2 && !document.querySelectorAll('.msg.assistant .body')[1].textContent.includes('생성 중')",timeout=120000)
        page.locator('#cancel').click()
        page.wait_for_function("document.querySelector('#send').disabled === false",timeout=10000)
        time.sleep(2)
        result['checks']['cancel_status']=get('/status')
        assert not result['checks']['cancel_status']['ready']
        mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)
        m=mobile.new_page();m.on('pageerror',lambda e:result['errors'].append(str(e)))
        m.goto('http://127.0.0.1:8000/mobile',wait_until='networkidle')
        result['checks']['mobile_title']=m.title()
        result['checks']['mobile_no_horizontal_overflow']=m.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert result['checks']['mobile_no_horizontal_overflow']
        m.locator('summary').click();m.locator('#maxTokens').fill('128')
        m.locator('#prompt').fill('두 수를 더하는 파이썬 add(a, b) 함수를 코드만 작성해 줘.')
        m.locator('#send').click();m.wait_for_function("document.querySelector('#send').disabled === false",timeout=120000)
        result['checks']['mobile_code_reply']=m.locator('.msg.assistant .body').last.inner_text()
        assert 'def add' in result['checks']['mobile_code_reply']
        m.screenshot(path=str(ROOT/'mobile-verified.png'),full_page=True)
        result['checks']['recovered_after_cancel']=get('/status')
        assert result['checks']['recovered_after_cancel']['ready']
        result['checks']['iphone_safari']='Not tested on physical Safari; mobile viewport tested in Chromium.'
        browser.close()
except Exception as exc:
    result['fatal_error']=repr(exc)
    raise
finally:
    stop.set()
    result['worker_samples']=samples
    if samples:result['cpu_summary']={'mean_worker_cpu_percent_of_machine':statistics.mean(x['worker_cpu_percent_of_machine'] for x in samples),'peak_worker_cpu_percent_of_machine':max(x['worker_cpu_percent_of_machine'] for x in samples),'peak_worker_rss_gib':max(x['worker_rss_gib'] for x in samples)}
    (ROOT/'ui-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checks':result['checks'],'errors':result['errors'],'cpu_summary':result.get('cpu_summary')},ensure_ascii=True,indent=2))
