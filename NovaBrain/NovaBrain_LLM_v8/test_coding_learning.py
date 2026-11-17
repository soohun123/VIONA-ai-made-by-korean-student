"""Lifecycle regressions; no generated code or real training is executed here."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import coding_learning as learning


class CodingLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Path(self.temp.name)/'learning';self.store.mkdir()
        patcher=patch.object(learning,'STORE',self.store);patcher.start();self.addCleanup(patcher.stop)
        self.identifier='a'*32;self.run=self.store/'runs'/self.identifier;self.run.mkdir(parents=True)
        self.report={'id':self.identifier,'state':'cancelled','phase':'stopped','completed':2,'total':2,
                     'started':10,'first_passed':1,'repaired_passed':1,'parts':{},'teacher_examples':1,'coaching_count':1}
        self.save('report.json',self.report)
        self.save('config.json',{'parts':['basics'],'repairs':1,'training_seconds':300})
        (self.run/'teaching.jsonl').write_text('{}\n{}\n',encoding='utf-8')
        learning.write(self.store/'current.json',{'id':self.identifier,'pid':99999999,'created':1})

    def save(self,name,data):learning.write(self.run/name,data)

    def test_finished_process_does_not_erase_record(self):
        with patch.object(learning,'alive',return_value=False):
            report=learning.current()
            self.assertEqual(report['completed'],2)
            self.assertEqual(report['state'],'cancelled')
            self.assertFalse(report['process_alive'])
            self.assertTrue(learning.details(self.identifier)['can_resume'])

    def test_interrupted_process_is_reported_without_rewriting_history(self):
        self.report['state']='running';self.save('report.json',self.report)
        before=(self.run/'report.json').read_bytes()
        with patch.object(learning,'alive',return_value=False):self.assertEqual(learning.current()['state'],'interrupted')
        self.assertEqual((self.run/'report.json').read_bytes(),before)

    def test_starting_registration_blocks_duplicate_start(self):
        self.report['state']='starting';self.save('report.json',self.report)
        learning.write(self.store/'starting.json',{'id':self.identifier,'pid':123,'created':1})
        with patch.object(learning,'alive',return_value=True),patch('text_training_runtime.active_training',return_value=None),patch.object(learning,'spawn') as spawn:
            with self.assertRaisesRegex(ValueError,'이미'):learning.start({'parts':['basics']})
            spawn.assert_not_called()

    def test_resume_refuses_partial_or_missing_teaching(self):
        (self.run/'teaching.jsonl').write_text('{}\n',encoding='utf-8')
        with patch.object(learning,'alive',return_value=False),patch('text_training_runtime.active_training',return_value=None):
            with self.assertRaisesRegex(ValueError,'교재 수'):learning.resume(self.identifier,300)

    def test_resume_preserves_old_scores_and_uses_separate_run(self):
        before={p.name:p.read_bytes() for p in self.run.iterdir()}
        fake=Mock();fake.pid=123;process=Mock();process.create_time.return_value=20
        with patch.object(learning,'alive',return_value=False),patch('text_training_runtime.active_training',return_value=None),patch.object(learning.subprocess,'Popen',return_value=fake),patch.object(learning.psutil,'Process',return_value=process):
            result=learning.resume(self.identifier,300)
        self.assertNotEqual(result['id'],self.identifier)
        new=self.store/'runs'/result['id']
        report=json.loads((new/'report.json').read_text(encoding='utf-8'))
        self.assertTrue(report['practice_reused'])
        self.assertEqual(report['first_passed'],1)
        self.assertEqual((new/'teaching.jsonl').read_bytes(),before['teaching.jsonl'])
        for name,value in before.items():self.assertEqual((self.run/name).read_bytes(),value)
        self.assertTrue((self.store/'starting.json').exists())


if __name__=='__main__':unittest.main()
