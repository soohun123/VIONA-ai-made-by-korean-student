from pathlib import Path
root=Path(__file__).resolve().parent
p=root/'app.js'
s=p.read_text(encoding='utf-8')
s=s.replace("$('cancel').onclick=()=>{controller?.abort()}","$('cancel').onclick=()=>{fetch('/admin/cancel',{method:'POST'}).catch(()=>{});controller?.abort()}")
s=s.replace("너는 NovaBrain이라는 한국어 중심의 정확한 로컬 AI다. 모르면 모른다고 답하고 코드는 실행 가능한 형태로 작성한다.","너는 NovaBrain이라는 한국어 로컬 AI다. 한국어 질문에는 한국어로 답하고 파이썬 코드를 작성한다. 네게는 웹 검색, 파일 조작, 이미지 생성 도구가 없다. 모르면 모른다고 답한다.")
s=s.replace("Number(el.value)||def","(Number.isFinite(Number(el.value))?Number(el.value):def)")
s=s.replace("status();document.addEventListener", "status();setInterval(()=>{if(!document.hidden)status()},5000);document.addEventListener")
p.write_text(s,encoding='utf-8')
for name in ('index.html','mobile.html'):
    p=root/name;s=p.read_text(encoding='utf-8')
    s=s.replace('/mobileDesktop','모바일 화면').replace('/Mobile','PC 화면')
    s=s.replace('width=device-width,initial-scale=1','width=device-width,initial-scale=1,viewport-fit=cover')
    s=s.replace('</small></details>',' 컨텍스트 기본 8,192 · 최대 32,768. 최대 응답은 입력과 함께 컨텍스트 안에 들어가야 합니다.</small></details>')
    if name=='mobile.html':
        s=s.replace('#log{height:calc(100dvh - 265px);','#log{height:calc(100vh - 265px);height:calc(100dvh - 265px);')
    p.write_text(s,encoding='utf-8')
