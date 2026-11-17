import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import training_store as s
import server
from fastapi.testclient import TestClient
from PIL import Image

class CumulativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'source';self.root.mkdir();self.loras=self.root/'models/loras';self.loras.mkdir(parents=True)
        self.datasets=self.root/'data/datasets';self.datasets.mkdir(parents=True)
        for name,value in [('ROOT',self.root),('LORAS',self.loras),('DATASETS',self.datasets)]:
            p=patch.object(s,name,value);p.start();self.addCleanup(p.stop)
        self.parent='a'*32;self.job='b'*32
        (self.loras/(self.parent+'.safetensors')).write_bytes(b'original')
        (self.loras/(self.parent+'.json')).write_text(json.dumps({'adapter_id':self.parent,'name':'old','steps':180,'dataset_id':'one'}))
    def stages(self):
        a=self.loras/'native.tmp';b=self.loras/'training.tmp';a.write_bytes(b'new');b.write_bytes(b'raw');return a,b
    def test_keep_previous_creates_new_id_and_preserves_bytes(self):
        a,b=self.stages();result=s.publish_adapter(self.job,self.parent,True,{'name':'new'},a,b)
        self.assertEqual(result['adapter_id'],self.job);self.assertEqual((self.loras/(self.parent+'.safetensors')).read_bytes(),b'original')
    def test_replace_keeps_id_and_makes_safety_backup(self):
        a,b=self.stages();result=s.publish_adapter(self.job,self.parent,False,{'name':'new'},a,b)
        self.assertEqual(result['adapter_id'],self.parent);self.assertEqual((self.loras/(self.parent+'.safetensors')).read_bytes(),b'new')
        backup=self.root.parent/result['replaced_version_backup'];self.assertEqual((backup/(self.parent+'.safetensors')).read_bytes(),b'original')
    def test_failed_commit_restores_all_existing_files(self):
        a,b=self.stages();replace=s._replace
        def fail(source,target):
            if str(target).endswith('.json'):raise OSError('fixture metadata failure')
            return replace(source,target)
        with patch.object(s,'_replace',side_effect=fail):
            with self.assertRaises(OSError):s.publish_adapter(self.job,self.parent,False,{'name':'new'},a,b)
        self.assertEqual((self.loras/(self.parent+'.safetensors')).read_bytes(),b'original')
        self.assertEqual(s.adapter_metadata(self.parent)['name'],'old')
        self.assertFalse((self.loras/(self.parent+'.training.safetensors')).exists())
    def test_rename_preserves_id_weights_and_original_metadata_backup(self):
        s.rename('adapter',self.parent,'  새 이름  ')
        self.assertEqual(s.adapter_metadata(self.parent)['name'],'새 이름')
        self.assertEqual((self.loras/(self.parent+'.safetensors')).read_bytes(),b'original')
        self.assertEqual(len(list((self.root/'data/training/metadata-backups').glob('*.json'))),1)
    def test_whitespace_and_path_names_are_rejected(self):
        for name in ('','   '):
            with self.assertRaises(ValueError):s.rename('adapter',self.parent,name)
        with self.assertRaises(ValueError):s.rename('adapter','../secret','new')
    def test_replay_deduplicates_and_keeps_validation_out_of_training(self):
        for identifier,records in [('one',[('old.png','train'),('same.png','validation')]),('two',[('new.png','train'),('same.png','train')])]:
            directory=self.datasets/identifier;directory.mkdir();rows=[]
            for filename,split in records:
                image=self.root/filename;Image.new('RGB',(16,16),{'old.png':'red','new.png':'blue','same.png':'green'}[filename]).save(image);rows.append({'image':filename,'relative_to_root':True,'caption':'test','split':split})
            (directory/'dataset.json').write_text(json.dumps({'id':identifier,'name':identifier,'records':rows}))
        combined,history=s.collect_training_records('two',{'dataset_id':'one'})
        self.assertEqual(history,['one','two']);self.assertEqual(len(combined['records']),3)
        self.assertEqual(next(r for r in combined['records'] if r['image']=='same.png')['split'],'validation')
    def test_rename_api_requires_local_token(self):
        self.assertEqual(TestClient(server.app).patch('/api/training/adapter/'+self.parent,json={'name':'new'}).status_code,403)

if __name__=='__main__':unittest.main()
