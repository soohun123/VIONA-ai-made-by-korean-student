"""Save generated HTML as data; never render or execute it automatically."""
import hashlib,re,uuid
from pathlib import Path

def extract_html(reply):
    blocks=re.findall(r'```html\s*\n(.*?)```',str(reply),re.S|re.I)
    text=(blocks[0] if blocks else str(reply)).strip()
    if '\x00' in text or len(text.encode('utf-8'))>2_000_000:raise ValueError('HTML 파일 크기나 내용을 확인해 주세요.')
    if not text.startswith('<'):raise ValueError('저장할 HTML 코드가 없습니다.')
    if re.search(r'<html\b',text,re.I):
        if not re.search(r'</html\s*>',text,re.I):raise ValueError('HTML 문서가 잘렸습니다. 완성된 코드를 요청해 주세요.')
    else:text='<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VIONA</title></head><body>\n'+text+'\n</body></html>'
    return text

def save_html(reply,directory):
    content=extract_html(reply);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/('VIONA-'+uuid.uuid4().hex[:12]+'.html')
    with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(content)
    data=path.read_bytes()
    return {'file':str(path),'filename':path.name,'html':content,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'automatically_executed':False}
