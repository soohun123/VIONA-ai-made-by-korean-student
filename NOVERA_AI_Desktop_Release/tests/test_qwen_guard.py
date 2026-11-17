import sys,unittest,tempfile,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from qwen_guard import budget,inspect_python,coding_request,html_request
from website_sync import read_release

class GuardTests(unittest.TestCase):
 def test_explanation_requests_do_not_force_generation(self):
  self.assertFalse(coding_request('이 Python 코드를 설명해 줘'))
  self.assertFalse(html_request('이 HTML 코드를 분석해 줘'))
  self.assertTrue(coding_request('Python 코드를 분석하고 수정해 줘'))
 def test_long_question_is_rejected_not_sliced(self):
  messages=[{'role':'system','content':'s'},{'role':'user','content':'x'*3000}]
  with self.assertRaises(ValueError):budget(messages,lambda b,**k:list(b),2048,512)
  self.assertEqual(len(messages[-1]['content']),3000)
 def test_old_turns_removed_latest_preserved(self):
  messages=[{'role':'system','content':'s'},{'role':'user','content':'old'*300},{'role':'assistant','content':'old'*300},{'role':'user','content':'latest'}]
  kept,_,meta=budget(messages,lambda b,**k:list(b),2048,512)
  self.assertEqual(kept[-1]['content'],'latest');self.assertGreater(meta['removed_messages'],0)
 def test_bad_code_detected_without_execution(self):
  r=inspect_python('```python\ndef f(x)\n return x\n```','Write Python function f(x)')
  self.assertTrue(r['issues']);self.assertFalse(r['executed'])
 def test_placeholders_and_mutable_defaults(self):
  for code in ['def f(x):\n pass','def f(x=[]):\n return x']:
   self.assertTrue(inspect_python(code,'Write Python function f(x)')['issues'])
 def test_legitimate_ellipsis_type_and_exception_class(self):
  self.assertFalse(inspect_python('from typing import Tuple\nclass E(Exception):\n pass\ndef f(x: Tuple[int, ...]):\n return x','Write Python function f(x)')['issues'])
 def test_signature_and_truncation(self):
  r=inspect_python('def wrong(x):\n return x','Write Python function wanted(x)','length');self.assertEqual(len(r['issues']),2)
 def test_release_path_cannot_escape_project(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);rid='a'*32;folder=root/'data/deployments'/rid;folder.mkdir(parents=True)
   (folder.parent/'current.json').write_text(json.dumps({'id':rid}));(folder/'manifest.json').write_text(json.dumps({'name':'test','models':[{'id':'x','kind':'text','name':'x','path':'../../outside.gguf'}],'hashes':{}}))
   with self.assertRaises(ValueError):read_release(root)

if __name__=='__main__':unittest.main()
