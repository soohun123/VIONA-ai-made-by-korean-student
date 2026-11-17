"""Data integrity and configuration checks; actual inference has a separate EXE test."""
import os,sys,tempfile,unittest,json
import io
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
os.environ['NOVERA_DATA_DIR']=tempfile.mkdtemp(prefix='novera-unit-')
import desktop

class DesktopTests(unittest.TestCase):
 def setUp(self):self.c=desktop.Controller()
 def tearDown(self):self.c.close()
 def test_checksum_rejects_modified_model(self):
  p=desktop.DATA/'fixture.gguf';p.write_bytes(b'GGUF-original');h=desktop.digest(p)
  row={'source':str(p),'sha256':h};self.assertEqual(self.c.verified(row),p)
  p.write_bytes(b'GGUF-modified-more')
  with self.assertRaises(ValueError):self.c.verified(row)
 def test_history_round_trip_preserves_korean(self):
  rows=[{'id':'test','title':'한국어 대화','messages':[{'role':'user','content':'안녕하세요'}]}]
  self.assertTrue(self.c.save_history(rows)['ok']);self.assertEqual(self.c.history(),rows)
 def test_configuration_clamps_resources(self):
  self.assertTrue(self.c.configure({'mode':'cpu','threads':100,'context':999999,'strength':100})['ok'])
  self.assertEqual(self.c.settings['threads'],6);self.assertEqual(self.c.settings['context'],32768);self.assertEqual(self.c.settings['strength'],1.5)
 def test_invalid_mode_rejected_without_overwrite(self):
  old=self.c.settings.copy();self.assertIn('error',self.c.configure({'mode':'invalid'}));self.assertEqual(old,self.c.settings)
 def test_api_does_not_expose_process_or_window(self):
  api=desktop.Bridge(self.c);self.assertFalse(hasattr(api,'window'));self.assertFalse(hasattr(api,'proc'));self.assertFalse(hasattr(api,'models'))
 def test_low_ram_blocks_loading_without_starting_worker(self):
  with patch('desktop.psutil.virtual_memory',return_value=SimpleNamespace(available=2*2**30,used=13*2**30)):
   with self.assertRaises(ValueError):self.c.load_model()
   self.assertIsNone(self.c.proc)
 def test_one_bounded_repair_preserves_original_spec(self):
  self.c.proc=SimpleNamespace(stdin=io.StringIO(),pid=99999999,poll=lambda:None)
  for value in [{'token':'def f(x)\n return x'},{'done':True,'finish_reason':'stop'},{'token':'def f(x):\n return x'},{'done':True,'finish_reason':'stop'}]:self.c.q.put(value)
  with patch.object(self.c,'load_model'):
   result=self.c.chat([{'role':'user','content':'Write Python function f(x) that returns x.'}])
  self.assertEqual(len(result['attempts']),2);self.assertFalse(result['code_checks']['issues'])
  requests=[json.loads(x) for x in self.c.proc.stdin.getvalue().splitlines()]
  self.assertIn('returns x',requests[-1]['messages'][-1]['content'])
 def test_worse_repair_does_not_replace_existing_code(self):
  first='def f(x=[]):\n return x';self.c.proc=SimpleNamespace(stdin=io.StringIO(),pid=99999999,poll=lambda:None)
  for value in [{'token':first},{'done':True,'finish_reason':'stop'},{'token':'I cannot write code.'},{'done':True,'finish_reason':'stop'}]:self.c.q.put(value)
  with patch.object(self.c,'load_model'):result=self.c.chat([{'role':'user','content':'Write Python function f(x).'}])
  self.assertEqual(result['text'],first);self.assertTrue(result['code_checks']['issues'])
 def test_deployment_sync_preserves_account_history(self):
  api=desktop.Bridge(self.c);api._user={'id':'developer','login':'fixture','role':'developer'}
  saved=[{'id':'saved','title':'keep','messages':[{'role':'user','content':'keep my account history'}]}]
  desktop.atomic(api._accounts.history_path(api._user),saved)
  with patch.object(self.c,'sync_web',return_value={'ok':True,'bootstrap':{'history':[]}}):result=api.sync_web()
  self.assertEqual(result['bootstrap']['history'],saved)

if __name__=='__main__':unittest.main()
