"""Bounded context and static checks. Never executes generated Python."""
import ast,json,re
from coding_policy import PYTHON_SYSTEM,CONTRACT_CHECKS

def analysis_only(text):
    return bool(re.search(r'설명|분석|리뷰|검토|explain|review|analy[sz]e|what does',text,re.I) and not re.search(r'작성|구현|수정|고쳐|만들|짜\s*줘|완성|implement|write|fix|create|build',text,re.I))

def coding_request(text):
    if analysis_only(text):return False
    return bool(re.search(r'python|파이썬',text,re.I) and re.search(r'함수|구현|코드|작성|수정|function|implement|write|fix|code',text,re.I))

def html_request(text):
    if analysis_only(text):return False
    return bool(re.search(r'html|웹\s*페이지|웹사이트',text,re.I) and re.search(r'만들|짜|작성|구현|코드|create|build|write|code',text,re.I))

def system_message(text,extra=''):
    if html_request(text):return 'Return one complete self-contained HTML5 document in a single html code block, including inline CSS and needed JavaScript. Use the user language for visible text. Close the html tag. No placeholders or external dependencies. Do not claim browser tests were run. '+str(extra)[:2000]
    if coding_request(text):
        if re.search(r'설명|분석|리뷰|검토|explain|review|analy[sz]e',text,re.I):return CONTRACT_CHECKS+' Provide the requested explanation and complete implementation in a Python code block. Do not claim unperformed tests. '+str(extra)[:2000]
        return PYTHON_SYSTEM+' '+str(extra)[:2000]
    base='You are VIONA, a helpful assistant. Answer Korean requests in Korean. Distinguish verified facts from assumptions. '
    return base+str(extra)[:4000]

def budget(messages,tokenize,context,requested):
    kept=[dict(m) for m in messages];maximum=min(2048,max(1,int(requested)),context//2);removed=0
    def estimate():return len(tokenize(json.dumps(kept,ensure_ascii=False).encode('utf-8'),add_bos=False))+32*len(kept)+128
    while estimate()+maximum>context and len(kept)>2:
        kept.pop(1);removed+=1
        while len(kept)>2 and kept[1]['role']=='assistant':kept.pop(1);removed+=1
    if estimate()+maximum>context:raise ValueError('최근 질문이 모델 입력 한도를 넘습니다. 원문을 임의로 자르지 않았습니다. 질문을 나눠 주세요.')
    return kept,maximum,{'removed_messages':removed,'estimated_input_tokens':estimate(),'count_method':'JSON tokenizer plus conservative template reserve; not exact template count'}

def inspect_python(reply,prompt,finish_reason=None):
    if not coding_request(prompt):return {'checked':False,'issues':[],'executed':False,'syntax_valid':None}
    blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',reply,re.S|re.I)
    code='\n\n'.join(blocks) if blocks else reply.strip();issues=[]
    if finish_reason=='length':issues.append('출력 토큰 한도로 답변이 잘렸습니다.')
    syntax_valid=False
    try:
        tree=ast.parse(code);compile(tree,'<generated>','exec')
        syntax_valid=True
        if not tree.body:issues.append('Python 구현이 비어 있습니다.')
        if any(isinstance(n,ast.FunctionDef) and len(n.body)==1 and (isinstance(n.body[0],ast.Pass) or isinstance(n.body[0],ast.Expr) and isinstance(n.body[0].value,ast.Constant) and n.body[0].value.value is Ellipsis or isinstance(n.body[0],ast.Raise) and isinstance(n.body[0].exc,ast.Call) and isinstance(n.body[0].exc.func,ast.Name) and n.body[0].exc.func.id=='NotImplementedError') and not any(isinstance(d,ast.Name) and d.id=='abstractmethod' for d in n.decorator_list) for n in ast.walk(tree)):
            issues.append('미완성 구현(pass/ellipsis/NotImplementedError)이 있습니다.')
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(isinstance(x,(ast.List,ast.Dict,ast.Set)) for x in node.args.defaults):issues.append('변경 가능한 기본 인자는 호출 사이에 상태를 공유할 수 있습니다.')
        wanted=re.findall(r'(?:def\s+|function\s+)([A-Za-z_]\w*)\s*\(',prompt)
        names={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for name in wanted:
            if name not in names:issues.append('요청한 함수가 없습니다: '+name)
    except (SyntaxError,ValueError,RecursionError) as e:issues.append('Python 문법/컴파일 검사: '+str(e)[:300])
    return {'checked':True,'issues':list(dict.fromkeys(issues)),'executed':False,'syntax_valid':syntax_valid,'functional_correctness':'not verified'}
