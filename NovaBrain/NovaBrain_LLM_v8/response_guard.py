"""Bound repeated prose without treating ordinary code indentation as a loop."""
import re
FACTUAL_RULES = ('Answer the latest request directly using the available information. Do not repeat the user question as your answer or ask the same clarification again. Ask at most one concise clarification only when essential. State uncertainty when evidence is missing. Never invent sources, tool results, tests, downloads, or completed actions. Acknowledge that local files and current facts need actual verification. ')
def repeating(text):
    tail=text[-4096:]
    if text.count('```')%2:return False
    compact=re.sub(r'\s+',' ',tail).strip()
    for size in range(24,min(300,len(compact)//4)+1):
        block=compact[-size:]
        if len(set(block))>=8 and compact.endswith(block*4):return True
    sentences=[re.sub(r'\s+','',s) for s in re.split(r'(?<=[.!?。？！])\s*|\n+',tail) if len(s.strip())>=16]
    return len(sentences)>=4 and len(set(sentences[-4:]))==1

def grounding_reply(messages):
    if any(m.get('role')=='tool' for m in messages):return None
    users=[m.get('content','') for m in messages if m.get('role')=='user']
    text=users[-1] if users else ''
    if re.search(r'\d+(?:\.\d+)?\s*(?:°\s*C|도|℃)',text,re.I):return None
    if re.search(r'코드|작성|구현|만들|방법|어떻게|script|how',text,re.I):return None
    if re.search(r'CPU|GPU|프로세서|그래픽',text,re.I) and re.search(r'온도|temperature',text,re.I) and re.search(r'현재|지금|내 컴퓨터|내 PC|my (?:computer|pc)|current',text,re.I):
        return '제공된 센서 측정값이 없어 현재 온도를 알 수 없습니다. 모니터링 도구의 실제 측정값을 알려주시면 해석을 도와드릴 수 있습니다.'
    if re.search(r'테스트|검사|test',text,re.I) and re.search(r'않았|안\s*(?:했|돌|하)|하지\s*않|실행\s*전|without',text,re.I) and re.search(r'통과|성공|pass',text,re.I):
        return '실제 테스트 실행 결과가 없으면 통과했다고 말할 수 없습니다. 파일을 읽는 것만으로도 테스트 성공 여부를 확인할 수 없습니다.'
    return None
