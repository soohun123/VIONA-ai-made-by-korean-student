"""Conservative translation integrity checks; never silently repair dropped facts."""
import re

COUNTS = {'한':1,'두':2,'세':3,'네':4,'다섯':5,'여섯':6,'일곱':7,'여덟':8,'아홉':9,'열':10}
EN_COUNTS = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
COLORS = {'빨간':('red',),'빨강':('red',),'파란':('blue',),'파랑':('blue',),'초록':('green',),'녹색':('green',),
          '노란':('yellow',),'노랑':('yellow',),'흰색':('white',),'하얀':('white',),'검은':('black',),'검정':('black',),
          '분홍':('pink',),'보라':('purple','violet'),'회색':('gray','grey')}
NEGATIVE_KO = r'없이|없는|없게|하지\s*마|제외|빼고|말고|금지'
NEGATIVE_EN = r'\b(?:without|no|not|except|exclude|excluding|avoid|empty|remove|instead)\b|[- ]free\b'


def visual_glossary(source, translated):
    """Source-supported visual terms only; do not invent scene details."""
    text = translated
    if re.search(r'옆모습|측면',source):
        text = re.sub(r'\bnext door\b','side view',text,flags=re.I)
        if not re.search(r'\bside\b|\bprofile\b',text,re.I):text += ', side view'
    if '정면' in source and not re.search(r'front|head.on',text,re.I):text += ', front view'
    if '수채화' in source and 'watercolor' not in text.lower() and 'watercolour' not in text.lower():text += ', watercolor'
    if '사진' in source and not re.search(r'photo|photograph',text,re.I):text='a photograph of '+text.rstrip('.')
    return text


def korean_glossary(source, translated):
    if re.search(r'\brunway\b',source,re.I) and not re.search(r'\broad\b',source,re.I):
        translated=translated.replace('도로','활주로') if '활주로' not in translated else translated
    return translated


def explicit_translation(text):
    match=re.fullmatch(r'\s*(영어|한국어|한글)로\s*번역(?:해)?(?:줘|주세요)?\s*[:：\n]\s*(.+)',text,re.S)
    if not match:return None
    return ('en' if match[1]=='영어' else 'ko',match[2].strip())


def integrity_issues(source, translated, target):
    issues = []
    if not translated.strip():
        return ['Empty translation']
    numbers = set(re.findall(r'\d+(?:\.\d+)?', translated))
    if target == 'en':
        for word, number in EN_COUNTS.items():
            if re.search(r'\b'+word+r'\b', translated, re.I):numbers.add(str(number))
        for number in set(re.findall(r'\d+(?:\.\d+)?', source)):
            if number not in numbers:issues.append('Number missing: '+number)
        for word in re.findall(r'(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:대|개|명|마리|척|장)', source):
            number = COUNTS[word]
            if str(number) not in numbers and not (number==1 and re.search(r'\b(?:a|an)\b',translated,re.I)):
                issues.append('Count missing: '+str(number))
        for color, alternatives in COLORS.items():
            if color in source and not any(re.search(r'\b'+v+r'\b',translated,re.I) for v in alternatives):
                issues.append('Color missing: '+color)
        if re.search(NEGATIVE_KO,source) and not re.search(NEGATIVE_EN,translated,re.I):
            issues.append('Negation may be missing')
        for word, entity in (('보잉','Boeing'),('에어버스','Airbus')):
            if word in source and entity.casefold() not in translated.casefold():issues.append('Entity missing: '+entity)
        if re.search('[가-힣]',translated):issues.append('Untranslated Korean remains')
        if re.search(r'옆모습|측면',source) and not re.search(r'\bside\b|\bprofile\b',translated,re.I):issues.append('Side view missing')
        if '수채화' in source and not re.search(r'watercolou?r',translated,re.I):issues.append('Watercolor style missing')
    else:
        normalized = translated
        for word, number in COUNTS.items():
            if re.search(word+r'\s*(?:대|개|명|마리|척|장)',translated):numbers.add(str(number))
        for number in set(re.findall(r'\d+(?:\.\d+)?',source)):
            if number not in numbers:issues.append('Number missing: '+number)
        for word,number in EN_COUNTS.items():
            if re.search(r'\b'+word+r'\b',source,re.I) and str(number) not in numbers:issues.append('Count may be missing: '+word)
        if re.search(NEGATIVE_EN,source,re.I) and not re.search(r'없|않|아니|제외|금지|빈|비어|말고|대신',translated):issues.append('Negation may be missing')
    words = translated.lower().split()
    grams = [' '.join(words[i:i+5]) for i in range(max(0,len(words)-4))]
    if grams and max(grams.count(g) for g in set(grams)) > 2:issues.append('Repeated translation fragment')
    return list(dict.fromkeys(issues))
