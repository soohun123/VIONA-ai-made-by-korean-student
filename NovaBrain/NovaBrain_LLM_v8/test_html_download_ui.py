from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import json
ROOT=Path(__file__).resolve().parent
html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>VIONA HTML</title></head><body><h1>HTML 파일 저장 테스트</h1><p>VIONA가 작성한 HTML 코드를 파일로 받을 수 있습니다.</p></body></html>'
with sync_playwright() as p:
 browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(accept_downloads=True);page.goto('http://127.0.0.1:8000/',wait_until='networkidle')
 page.evaluate("text=>{const article=document.createElement('article');article.className='assistant';const pre=document.createElement('pre');const code=document.createElement('code');code.className='language-html';code.textContent=text;pre.append(code);article.append(pre);document.querySelector('#log').append(article)}",html)
 button=page.locator('#log .html-export');expect(button).to_be_visible()
 with page.expect_download() as info:button.click()
 download=info.value;out=ROOT/'html-download-example.html';download.save_as(str(out));assert out.read_text(encoding='utf-8')==html
 browser.close()
(ROOT/'html-download-validation.json').write_text(json.dumps({'passed':True,'real_html_file':str(out),'model_inference_used':False,'fixture_only':True},ensure_ascii=False,indent=2),encoding='utf-8');print('HTML DOWNLOAD PASS')
