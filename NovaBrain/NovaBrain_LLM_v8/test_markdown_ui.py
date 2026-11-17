"""Headless, isolated browser contexts; fixtures do not invoke the model."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data/validation/markdown-ui';OUT.mkdir(parents=True,exist_ok=True)
MARKDOWN='''## 비교 결과

| 항목 | CPU | GPU |
| --- | --- | --- |
| 적합한 작업 | 순차 처리 | 병렬 처리 |
| 메모리 | RAM | VRAM |

**확인 순서**

1. 여유 메모리를 확인합니다.
2. 작업에 맞는 장치를 선택합니다.

- 데이터 보존
- 필요한 변경만 적용

```python
print("<safe>")
```

<img src=x onerror="window.__unsafe=1">
[안전한 출처](https://example.com)
[위험 링크](javascript:alert(1))
![원격 이미지](https://example.com/tracker.png)
'''

def main():
    results=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
        for name,width,theme,route in [('desktop',1366,'dark','/'),('mobile',390,'light','/mobile')]:
            context=browser.new_context(viewport={'width':width,'height':950},reduced_motion='reduce')
            chat={'id':'markdown-test','title':'표·목록 확인','messages':[{'role':'user','content':'표와 목록으로 정리해줘'}, {'role':'assistant','content':MARKDOWN}]}
            context.add_init_script('localStorage.setItem("novabrain-v81-workspace",'+json.dumps(json.dumps({'chats':[chat],'current':chat['id']}))+');localStorage.setItem("novabrain-v81-settings",'+json.dumps(json.dumps({'theme':theme,'searchMode':'off'}))+');')
            page=context.new_page();errors=[];external=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda req:external.append(req.url) if not req.url.startswith('http://127.0.0.1:8000') else None)
            page.goto('http://127.0.0.1:8000'+route,wait_until='networkidle')
            body=page.locator('.message.assistant .message-body')
            expect(body.locator('table')).to_have_count(1)
            expect(body.locator('tbody tr')).to_have_count(2)
            expect(body.locator('ol li')).to_have_count(2)
            expect(body.locator('ul li')).to_have_count(2)
            expect(body.locator('pre code')).to_have_text('print("<safe>")\n')
            expect(body.locator('img,script,iframe')).to_have_count(0)
            assert page.evaluate('window.__unsafe') is None
            assert not body.locator('a[href^="javascript:"]').count()
            assert body.locator('a[href="https://example.com"]').get_attribute('rel')=='noopener noreferrer'
            assert not external,external
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Page overflows horizontally'
            page.locator('#scrollArea').evaluate('el=>el.scrollTop=0')
            page.screenshot(path=str(OUT/(name+'.png')))
            # The real send path renders multiple response chunks, without model use.
            events=[{'token':'| A | B |\n| --- | --- |\n'}, {'token':'| 1 | 2 |\n\n1. 첫 단계\n2. 다음 단계'}, {'done':True}]
            page.route('**/chat/stream',lambda r:r.fulfill(status=200,content_type='application/x-ndjson',body=''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events)))
            page.locator('#prompt').fill('표와 절차를 보여줘')
            page.locator('#send').click()
            expect(page.locator('#send')).to_be_enabled(timeout=10000)
            expect(page.locator('.message.assistant').last.locator('table')).to_have_count(1)
            expect(page.locator('.message.assistant').last.locator('ol li')).to_have_count(2)
            page.reload(wait_until='networkidle')
            expect(page.locator('.message.assistant').first.locator('table')).to_have_count(1)
            assert not errors,errors
            results.append({'viewport':name,'width':width,'theme':theme,'tables_lists_code':True,'unsafe_html_and_images_blocked':True,'streamed_rendering':True,'no_horizontal_page_overflow':True,'page_errors':errors})
            context.close()
        browser.close()
    (OUT/'results.json').write_text(json.dumps({'model_generation_tested':False,'checks':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
