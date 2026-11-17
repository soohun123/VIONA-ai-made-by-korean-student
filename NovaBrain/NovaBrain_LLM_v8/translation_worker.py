"""Offline Marian translation, CPU bounded, no Qwen prompt interpretation."""
import json
import os
import sys
import time
from pathlib import Path

from runtime_settings import read_settings
from translation_checks import integrity_issues,visual_glossary,korean_glossary
ROOT = Path(__file__).resolve().parent
threads = read_settings()['cpu_threads']
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  OMP_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS=str(threads))


def main():
    import torch
    from transformers import MarianMTModel, MarianTokenizer,M2M100ForConditionalGeneration,M2M100Tokenizer
    import sentencepiece
    from transformers.models.marian import tokenization_marian
    # SentencePiece 0.2.1's Windows filename loader rejects this installation's
    # Korean directory names. Python reads Unicode paths; the native tokenizer
    # receives identical serialized model bytes instead of a broken filename.
    tokenization_marian.load_spm = lambda path, options: sentencepiece.SentencePieceProcessor(
        model_proto=Path(path).read_bytes(), **(options or {}))
    torch.set_num_threads(threads); torch.set_num_interop_threads(1)
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    target = request['target']
    if target not in ('en','ko'):raise ValueError('Unsupported language direction')
    name = 'opus-mt-ko-en' if target == 'en' else 'm2m100_418M'
    base = ROOT / 'models/translation' / name
    generation_options={}
    if target=='en':
        tokenizer = MarianTokenizer.from_pretrained(base, local_files_only=True)
        model = MarianMTModel.from_pretrained(base, local_files_only=True, weights_only=True).eval()
    else:
        from transformers.models.m2m_100 import tokenization_m2m_100
        tokenization_m2m_100.load_spm=tokenization_marian.load_spm
        tokenizer=M2M100Tokenizer.from_pretrained(base,src_lang='en',tgt_lang='ko',local_files_only=True)
        model=M2M100ForConditionalGeneration.from_pretrained(base,local_files_only=True,weights_only=True).eval()
        generation_options['forced_bos_token_id']=tokenizer.get_lang_id('ko')
    results = []
    started = time.monotonic()
    for text in request['texts']:
        if not isinstance(text,str) or not text.strip() or len(text)>2000:raise ValueError('Invalid translation input')
        encoded = tokenizer(text, return_tensors='pt', truncation=False)
        if encoded['input_ids'].shape[1] > 480:raise ValueError('Translation input too long; split the text instead of truncating it')
        with torch.inference_mode():
            generated = model.generate(**encoded, max_new_tokens=384, num_beams=4, do_sample=False,**generation_options)
        raw = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        translated = visual_glossary(text,raw) if request.get('visual') and target=='en' else raw
        if target=='ko':translated=korean_glossary(text,translated)
        issues = integrity_issues(text,translated,target)
        if int(generated[0,-1]) != tokenizer.eos_token_id:issues.append('Output reached length limit')
        results.append({'source':text,'raw_translation':raw,'text':translated,'issues':issues,'verified_invariants':not issues,'output_id_count':len(generated[0])})
    source = json.loads((base/'source.json').read_text())
    output = {'target':target,'model':source,'cpu_threads':threads,'seconds':time.monotonic()-started,'items':results}
    Path(request['result_path']).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':main()
