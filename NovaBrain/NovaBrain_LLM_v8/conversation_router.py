"""Bounded conversation routing. Only explicit image requests launch a supported tool."""
import re
from assistant_tools import choose_skill
def domain(messages,selected='auto'):
    if selected!='auto':return selected
    users=[m.content for m in messages if m.role=='user'];latest=users[-1] if users else ''
    direct=choose_skill(latest,'auto')
    if direct!='general' or re.search(r'새\s*질문|다른\s*질문|주제.{0,5}바꾸',latest):return direct
    if len(latest)<160 and re.search(r'그거|그것|그걸|그럼|그러면|왜|예시|다시|좀\s*더|계속|아까|방금|이어서|고쳐|수정해|바꿔|변경해|더\s*짧게|설명해',latest):
        for old in reversed(users[:-1][-6:]):
            previous=choose_skill(old,'auto')
            if previous!='general':return previous
    return 'general'
def image_prompt(messages,mode='auto'):
    users=[m.content for m in messages if m.role=='user'];text=users[-1].strip() if users else ''
    if mode=='chat':return None
    if re.search(r'그리(?:지\s*마|지\s*않)|이미지.{0,12}(만들지|생성하지)|번역\s*[:：]|문장.{0,8}(교정|분석)|이미지\s*생성\s*(방법|원리|API)|코드.{0,8}(작성|구현)',text,re.I) and mode!='image':return None
    explicit=bool(re.search(r'그려\s*(줘|주세요|봐)|그림으로|이미지로.{0,8}(만들|생성)|(?:이미지|사진|그림|일러스트|포스터|로고).{0,30}(만들어|생성해|그려)',text))
    if re.fullmatch(r'취소|그만|아니요?|하지\s*마',text):return None
    if not explicit and messages[:-1] and messages[-2].role=='assistant' and messages[-2].content.startswith('어떤 이미지를 만들까요?'):
        if text in ('네','응','좋아'):return ''
        explicit=True
    if mode!='image' and not explicit:return None
    previous=[m.content for m in messages[:-1] if m.role in ('user','assistant')][-2:]
    generic=bool(re.fullmatch(r'(?:이미지|사진|그림)(?:를|을)?\s*(?:좀\s*)?(?:만들어\s*줘|생성해\s*줘|그려\s*줘)[.!?\s]*',text))
    if generic and not previous:return ''
    # Latest request stays first and cannot be displaced by the context size cap.
    return (text[:600]+('\n참고할 직전 대화:\n'+'\n'.join(previous)[-1100:] if previous and (generic or re.search(r'그거|그걸|그것|이걸|이것|아까|방금|장면|같은',text)) else ''))[:1500]
