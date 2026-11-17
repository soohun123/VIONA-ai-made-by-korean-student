import unittest,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from html_artifacts import save_html,extract_html
class HtmlTests(unittest.TestCase):
 def test_utf8_document_saved_as_real_file(self):
  with tempfile.TemporaryDirectory() as d:
   result=save_html('```html\n<!doctype html><html lang="ko"><body>안녕하세요</body></html>\n```',d)
   self.assertEqual(Path(result['file']).read_text(encoding='utf-8'),result['html']);self.assertFalse(result['automatically_executed'])
 def test_fragment_wrapped(self):self.assertIn('<html lang="ko">',extract_html('```html\n<h1>안녕</h1>\n```'))
 def test_cut_off_document_rejected(self):
  with self.assertRaises(ValueError):extract_html('<html><body>unfinished')
 def test_no_arbitrary_filename_or_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   first=save_html('<p>hello</p>',d);second=save_html('<p>hello</p>',d);self.assertNotEqual(first['file'],second['file'])
if __name__=='__main__':unittest.main()
