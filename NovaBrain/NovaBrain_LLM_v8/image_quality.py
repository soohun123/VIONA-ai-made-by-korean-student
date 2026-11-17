"""Local SD1.5 generation defaults and conservative visual-request cleanup."""
import re

DEFAULT_NEGATIVE = 'blurry, low quality, distorted geometry, malformed objects, duplicate parts, watermark'


def visual_subject(text):
    """Remove only a terminal request verb; retain subject, counts and style."""
    text=re.sub(r'(만들어|그려|보여)죠(?=[.!?~\s]*$)',r'\1줘',text)
    return re.sub(r'\s*(?:그려\s*주세요|그려줘|그려\s*줘|만들어\s*주세요|만들어줘|만들어\s*줘|생성해\s*주세요|생성해줘|보여\s*주세요|보여줘|가져와\s*주세요|가져와)[.!?~\s]*$', '', text.strip()).strip()


def simple_visual_translation(text):
    """Exact short requests only; richer descriptions use the local translator."""
    subject = re.sub(r'\s+', '', visual_subject(text)).rstrip('을를.!?')
    match = re.fullmatch(r'(비행기|항공기|여객기|자동차)(사진|이미지|그림)?', subject)
    if not match:
        return None
    noun = {'비행기': 'airplane', '항공기': 'aircraft', '여객기': 'passenger airplane', '자동차': 'car'}[match[1]]
    if match[2] == '사진':
        return 'a photograph of an ' + noun if noun[0] in 'aeiou' else 'a photograph of a ' + noun
    if match[2] == '그림':
        return 'an illustration of an ' + noun if noun[0] in 'aeiou' else 'an illustration of a ' + noun
    return ('an ' if noun[0] in 'aeiou' else 'a ') + noun
