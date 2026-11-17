import json,queue,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from fastapi.testclient import TestClient
import content_filter as f
import assistant_tools as a
import server
import media_jobs as m
import training_store as store

class ControlTests(unittest.TestCase):
    def test_detailed_style_preserves_limits_and_adds_examples(self):
        req=a.AssistantRequest(messages=[{'role':'user','content':'딕셔너리 자료구조를 설명해 주세요.'}],enhance=True,response_style='detailed',token_profile='full',max_tokens=2048)
        prepared,meta=a.enrich_request(req)
        self.assertEqual(prepared.max_tokens,2048);self.assertIn('구체적인 예시',prepared.messages[0].content)
        self.assertNotIn('필요한 이유만 짧게',prepared.messages[0].content)
    def test_gpu_range_is_validated_without_changing_config(self):
        for number in (0,27):
            with self.assertRaises(ValueError):server.RuntimeChange(gpu_mode='hybrid',gpu_blocks=number)
        self.assertEqual(server.RuntimeChange(gpu_mode='hybrid',gpu_blocks=20).gpu_blocks,20)
    def test_secret_split_across_stream_chunks_is_not_exposed(self):
        stream=f.TextStreamFilter();key='sk-fakeTestKey0123456789012345'
        self.assertEqual(stream.feed('api_key='+key[:8]),'')
        self.assertEqual(stream.feed(key[8:]),'')
        result=stream.feed('',final=True);self.assertNotIn(key,result);self.assertIn('가림',result)
    def test_privacy_masks_email_phone_and_secret(self):
        text='test.person@example.org 010-1234-5678 api_key=FAKE_API_KEY_VALUE'
        redacted=f.redact(text)
        for value in ('test.person','1234-5678','FAKE_API_KEY_VALUE'):self.assertNotIn(value,redacted)
    def test_health_and_prevention_are_not_keyword_blocked(self):
        self.assertIsNone(f.reason('성교육과 폭력 예방을 설명해 주세요.'))
        self.assertIsNotNone(f.reason('graphic gore'))
    def test_image_threshold_and_disabled_categories(self):
        config={**f.DEFAULT,'image_threshold':.65}
        self.assertIsNotNone(f.image_reason({'sexual':.8},config));self.assertIsNone(f.image_reason({'sexual':.5},config))
        self.assertIsNone(f.image_reason({'sexual':.9},{**config,'sexual':False}))
    def test_disabled_filter_retains_immediate_streaming(self):
        stream=f.TextStreamFilter({**f.DEFAULT,'privacy':False,'sexual':False,'violence':False})
        self.assertEqual(stream.feed('test'),'test')
    def test_input_and_output_privacy_at_real_server_route(self):
        key='sk-fakeTestKey0123456789012345';messages=queue.Queue()
        for value in [{'token':'api_key='+key[:10]},{'token':key[10:]},{'done':True,'metrics':{}}]:messages.put(json.dumps(value))
        proc=Mock();proc.poll.return_value=None
        with patch.object(server,'proc',proc),patch.object(server,'launch'),patch.object(server,'q',messages),patch.object(server,'guard',return_value=None):
            response=TestClient(server.app).post('/chat/stream',json={'messages':[{'role':'user','content':'Repeat '+key}],'max_tokens':32})
        self.assertEqual(response.status_code,200);self.assertNotIn(key,response.text);self.assertNotIn(key,proc.stdin.write.call_args.args[0])
    def test_content_block_does_not_launch_model(self):
        with patch.object(server,'launch') as launch:
            response=TestClient(server.app).post('/chat/stream',json={'messages':[{'role':'user','content':'pornography'}]})
        self.assertIn('검열',response.text);launch.assert_not_called()
    def test_training_and_filter_mutation_require_token(self):
        client=TestClient(server.app)
        self.assertEqual(client.post('/api/training/jobs',json={'dataset_id':'test'}).status_code,403)
        self.assertEqual(client.post('/api/content-filter',json={}).status_code,403)
    def test_model_paths_reject_traversal(self):
        for function in (store.dataset_path,store.adapter_path):
            with self.assertRaises(ValueError):function('../private')
    def test_blocked_generation_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);images=root/'images';images.mkdir();jobs=root/'jobs';jobs.mkdir()
            with patch.object(m,'ROOT',root),patch.object(m,'IMAGES',images),patch.object(m,'JOBS',jobs):
                manager=m.MediaJobs(threading.Lock(),Mock(),Mock(),Mock());manager.gate.acquire()
                exe=root/'media-runtime/cpu/sd-cli.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'')
                job={'id':'e'*32,'kind':'generate'};Image.new('RGB',(16,16),'red').save(images/(job['id']+'.png'))
                manager._run=Mock(return_value=(0,Path('log')));manager._screen=Mock(side_effect=RuntimeError('blocked'))
                manager._work(job,{'prompt':'test','size':256,'steps':4,'seed':42,'translate':False})
                self.assertEqual(job['state'],'error');self.assertIsNone(job['result']);self.assertFalse(manager.gate.locked())
                with self.assertRaises(ValueError):m.image_path(job['id'])
    def test_generated_image_caption_privacy_is_filtered(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);images=root/'images';images.mkdir();jobs=root/'jobs';jobs.mkdir()
            with patch.object(m,'ROOT',root),patch.object(m,'IMAGES',images),patch.object(m,'JOBS',jobs),patch.object(f,'settings',return_value=dict(f.DEFAULT)):
                manager=m.MediaJobs(threading.Lock(),Mock(),Mock(),Mock());manager.gate.acquire();manager._screen=Mock()
                job={'id':'f'*32,'kind':'read'};Image.new('RGB',(16,16),'red').save(images/(job['id']+'.png'))
                (jobs/(job['id']+'-vision-result.json')).write_text(json.dumps({'text':'contact test.person@example.org'}),encoding='utf-8')
                manager._run=Mock(return_value=(0,Path('log')))
                manager._work(job,{'image_id':job['id'],'prompt':'describe','translate':False})
                self.assertEqual(job['state'],'done');self.assertNotIn('test.person@example.org',job['result']['text'])

if __name__=='__main__':unittest.main()
