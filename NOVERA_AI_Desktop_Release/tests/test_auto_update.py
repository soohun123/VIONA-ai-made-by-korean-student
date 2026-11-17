import unittest,tempfile,sys,json,zipfile,hashlib,subprocess,os,stat
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import update_tools as tools

class UpdateTests(unittest.TestCase):
 def run_case(self,scenario):
  base=ROOT/'artifacts/update-tests';base.mkdir(exist_ok=True)
  with tempfile.TemporaryDirectory(dir=base) as temp:
   folder=Path(temp);self.assertTrue(folder.resolve().is_relative_to(ROOT))
   app=folder/'app';(app/'_internal').mkdir(parents=True);(app/'model-pack').mkdir()
   (app/'NOVERA_AI_Desktop.exe').write_bytes(b'fixture executable; never executed')
   (app/'app-version.json').write_text('{"version":"1.0.0"}')
   (app/'_internal/a.txt').write_bytes(b'old')
   (app/'model-pack/keep.gguf').write_bytes(b'user model stays')
   files={'_internal/a.txt':b'new','app-version.json':b'{"version":"1.1.0"}'}
   if scenario=='rollback':
    (app/'_internal/z.txt').write_bytes(b'locked');os.chmod(app/'_internal/z.txt',stat.S_IREAD);files['_internal/z.txt']=b'changed'
   if scenario=='zip_slip':files={'../escape.txt':b'bad','app-version.json':b'{"version":"1.1.0"}'}
   if scenario=='models':files={'model-pack/keep.gguf':b'bad','app-version.json':b'{"version":"1.1.0"}'}
   if scenario=='customized':(app/'_internal/a.txt').write_bytes(b'user custom content')
   rows=[]
   for name,data in files.items():
    path=app/name
    before=tools.digest(path) if path.exists() else None
    if scenario=='customized' and name=='_internal/a.txt':before=hashlib.sha256(b'old').hexdigest()
    rows.append({'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'before':{'1.0.0':before}})
   package=folder/'patch.zip'
   with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
    for name,data in files.items():z.writestr(name,data)
   manifest={'schema':1,'app_id':'NOVERA_AI_Desktop','version':'1.1.0','supported_versions':['1.0.0'],'files':rows,'package':'patch.zip','sha256':tools.digest(package)}
   envelope=tools.envelope(manifest)
   if scenario=='bad_signature':envelope['signature']='AA=='
   (folder/'channel.json').write_text(json.dumps(envelope),encoding='utf-8')
   if scenario=='bad_payload':package.write_bytes(b'corrupted after signing')
   result=folder/'result.json'
   p=subprocess.run([str(ROOT/'build/updater/NOVERA_Update.exe'),'--apply',str(folder/'channel.json'),str(app),str(result),'-1'],creationflags=subprocess.CREATE_NO_WINDOW,timeout=20)
   data=json.loads(result.read_text(encoding='utf-8'))
   self.assertEqual((app/'model-pack/keep.gguf').read_bytes(),b'user model stays')
   if scenario=='success':self.assertEqual(p.returncode,0);self.assertTrue(data['ok']);self.assertEqual((app/'_internal/a.txt').read_bytes(),b'new')
   else:
    self.assertNotEqual(p.returncode,0);self.assertFalse(data['ok']);self.assertEqual(json.loads((app/'app-version.json').read_text())['version'],'1.0.0')
    self.assertEqual((app/'_internal/a.txt').read_bytes(),b'user custom content' if scenario=='customized' else b'old')
    self.assertTrue(data['rollback_ok'])
   if scenario=='rollback':os.chmod(app/'_internal/z.txt',stat.S_IWRITE|stat.S_IREAD)
 def test_success(self):self.run_case('success')
 def test_signature(self):self.run_case('bad_signature')
 def test_package_checksum(self):self.run_case('bad_payload')
 def test_zip_slip(self):self.run_case('zip_slip')
 def test_model_protection(self):self.run_case('models')
 def test_user_changes_preserved(self):self.run_case('customized')
 def test_partial_apply_rollback(self):self.run_case('rollback')

if __name__=='__main__':unittest.main()
