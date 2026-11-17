import base64,io,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image
from fastapi.testclient import TestClient
import media_jobs as m
import server
import assistant_tools

class LocalMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patches=[patch.object(m,'ROOT',self.root),patch.object(m,'IMAGES',self.root/'images'),patch.object(m,'JOBS',self.root/'jobs')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def manager(self):
        manager=m.MediaJobs(threading.Lock(),Mock(),Mock(),Mock());manager._screen=Mock();return manager
    def test_upload_is_local_normalized_png_without_original_metadata(self):
        image=Image.new('RGB',(32,20),'red');data=io.BytesIO();exif=image.getexif();exif[270]='private metadata';image.save(data,format='JPEG',exif=exif)
        uploaded=m.save_upload('data:image/jpeg;base64,'+base64.b64encode(data.getvalue()).decode())
        with Image.open(m.image_path(uploaded['id'])) as saved:
            self.assertEqual(saved.size,(32,20));self.assertNotIn(270,saved.getexif())
    def test_svg_and_path_traversal_are_rejected(self):
        with self.assertRaises(ValueError):m.save_upload('data:image/svg+xml;base64,AAAA')
        for value in ('../private','https://example.com/test.png'):
            with self.assertRaises(ValueError):m.image_path(value)
    def test_huge_dimensions_are_rejected_before_decode(self):
        fake=Mock();fake.__enter__=Mock(return_value=SimpleNamespace(width=9000,height=9000));fake.__exit__=Mock(return_value=False)
        with patch.object(m.Image,'open',return_value=fake):
            with self.assertRaises(ValueError):m.save_upload('data:image/png;base64,AAAA')
    def test_memory_preflight_releases_generation_gate(self):
        manager=self.manager();manager.capabilities=Mock(return_value={'generation_ready':True})
        vm=SimpleNamespace(available=3*2**30,used=13.5*2**30)
        with patch.object(m.psutil,'virtual_memory',return_value=vm):
            with self.assertRaises(ValueError):manager.start('generate',{'prompt':'test'})
        self.assertFalse(manager.gate.locked())
    def test_synthetic_memory_guard_stops_native_job(self):
        manager=self.manager();manager._stop_process=Mock();process=Mock(pid=123);process.poll.return_value=None
        vm=SimpleNamespace(available=2.5*2**30,used=13.5*2**30)
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.psutil,'Process') as p,patch.object(m.psutil,'virtual_memory',return_value=vm):
            p.return_value.children.return_value=[]
            with self.assertRaises(RuntimeError):manager._run(['fake'],{'id':'a'*32},'fake')
        manager._stop_process.assert_called_once()
    def test_dead_launcher_children_are_still_reaped(self):
        manager=self.manager();manager.process=Mock();manager.process.poll.return_value=1;child=Mock();manager.children=[child]
        with patch.object(m.psutil,'wait_procs',return_value=([child],[])):manager._stop_process()
        child.terminate.assert_called_once();self.assertIsNone(manager.process)
    def test_incomplete_old_job_becomes_terminal_on_restart(self):
        (self.root/'jobs').mkdir();path=self.root/'jobs'/('a'*32+'.json');path.write_text(json.dumps({'id':'a'*32,'state':'running'}))
        self.manager();self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['state'],'error')
    def test_failed_image_job_restores_chat_and_releases_gate(self):
        manager=self.manager();manager.gate.acquire();manager._run=Mock(return_value=(1,Path('fake')));manager._stop_process=Mock()
        exe=self.root/'media-runtime/cpu/sd-cli.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'')
        job={'id':'b'*32,'kind':'generate','state':'queued'}
        manager._work(job,{'prompt':'test','size':256,'steps':4,'seed':42,'translate':False})
        self.assertEqual(job['state'],'error');manager.reload.assert_called_once();self.assertFalse(manager.gate.locked())
    def test_media_mutation_requires_token_and_size_limit(self):
        client=TestClient(server.app)
        self.assertEqual(client.post('/api/media/jobs',json={'kind':'generate','prompt':'test'}).status_code,403)
        response=client.post('/api/media/jobs',json={'kind':'generate','prompt':'test','size':2048},headers={'x-novabrain-token':server.TOOL_TOKEN})
        self.assertEqual(response.status_code,422)
    def test_computer_use_router_is_silent(self):
        req=assistant_tools.AssistantRequest(messages=[{'role':'user','content':'컴퓨터 사용'}],enhance=True,plugin_id='computer-use')
        _,context=assistant_tools.enrich_request(req)
        self.assertEqual(context['direct_reply'],'');self.assertEqual(context['client_action'],'desktop')
    def test_cancelled_translation_stops_partial_worker_stream(self):
        with patch.object(server,'launch'),patch.object(server,'proc',Mock()),patch.object(server,'stop') as stop:
            with self.assertRaises(InterruptedError):server.local_text_task('test','en',lambda:True)
            stop.assert_called_once_with('로컬 번역 취소')
    def test_chat_restore_failure_is_reported_as_error(self):
        manager=self.manager();manager.gate.acquire();manager.reload.side_effect=RuntimeError('fixture restore failure')
        manager._run=Mock(return_value=(0,Path('fake')));manager._stop_process=Mock()
        exe=self.root/'media-runtime/cpu/sd-cli.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'')
        image=self.root/'images'/('c'*32+'.png');Image.new('RGB',(16,16),'red').save(image)
        job={'id':'c'*32,'kind':'generate','state':'queued'}
        manager._work(job,{'prompt':'test','size':256,'steps':4,'seed':42,'translate':False})
        self.assertEqual(job['state'],'error');self.assertEqual(job['restore_error'],'fixture restore failure')
        self.assertIsNotNone(job['result']);self.assertFalse(manager.gate.locked())
    def test_cuda_failure_falls_back_to_cpu_and_restores_chat(self):
        manager=self.manager();manager.gate.acquire();manager._run=Mock(side_effect=[(1,Path('cuda-log')),(0,Path('cpu-log'))]);manager._stop_process=Mock()
        for backend in ('cuda','cpu'):
            exe=self.root/'media-runtime'/backend/'sd-cli.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'')
        Image.new('RGB',(16,16),'red').save(self.root/'images'/('d'*32+'.png'))
        job={'id':'d'*32,'kind':'generate','state':'queued'}
        manager._work(job,{'prompt':'test','size':256,'steps':4,'seed':42,'translate':False})
        self.assertEqual(job['state'],'done');self.assertEqual(job['result']['backend'],'cpu')
        self.assertEqual(manager._run.call_count,2);manager.reload.assert_called_once();self.assertFalse(manager.gate.locked())

if __name__=='__main__':unittest.main(verbosity=2)
