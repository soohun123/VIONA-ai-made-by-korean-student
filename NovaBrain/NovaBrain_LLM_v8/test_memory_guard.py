"""Regression tests for zero-RSS idle samples causing false leak resets."""
import io,json,queue,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import server

class MemoryGuardTests(unittest.TestCase):
    def setUp(self):
        server.samples.clear()
        server.proc=Mock(pid=42);server.proc.poll.return_value=None
        server.ready={'ready':True};server.worker_loaded_at=0
        self.vm=SimpleNamespace(total=16*2**30,used=10*2**30,available=6*2**30)
    def guard(self,now,rss):
        with patch.object(server.psutil,'virtual_memory',return_value=self.vm),patch.object(server,'rss_gb',return_value=rss),patch.object(server.time,'monotonic',return_value=now):
            return server.guard()
    def test_idle_does_not_establish_zero_baseline(self):
        server.proc=None;server.ready=None
        server.samples.append((0,0,8))
        self.assertIsNone(self.guard(180,0))
        self.assertEqual(len(server.samples),0)
    def test_launch_discards_idle_and_previous_worker_samples(self):
        server.proc=None;server.ready=None
        server.samples.append((0,0,8))
        responses=queue.Queue();responses.put(json.dumps({'ready':True,'limit':32768}))
        process=Mock(pid=42)
        with patch.object(server,'layers_for_mode',return_value=0),patch.object(server.psutil,'Process'),patch.object(server.queue,'Queue',return_value=responses),patch.object(server.subprocess,'Popen',return_value=process),patch.object(server.threading,'Thread'),patch.object(server,'memory',return_value={'available_gb':8}),patch.object(server.time,'monotonic',return_value=200):
            server.launch()
        self.assertEqual(list(server.samples),[])
        self.assertEqual(server.worker_loaded_at,200)
    def test_warmup_zero_sample_is_not_a_leak(self):
        server.samples.append((0,0,8))
        self.assertIsNone(self.guard(180,1.86))
    def test_stable_loaded_model_is_not_a_leak(self):
        server.samples.append((31,1.86,10))
        self.assertIsNone(self.guard(180,1.87))
    def test_real_growth_after_warmup_is_still_detected(self):
        server.samples.append((31,1.86,10))
        self.assertIn('누수 의심',self.guard(152,3.0))
    def test_absolute_rss_protection_remains_during_warmup(self):
        self.assertIn('워커 상한',self.guard(1,11))
    def test_system_memory_protection_remains_without_worker(self):
        server.proc=None;server.ready=None
        self.vm.used=int(13.5*2**30);self.vm.available=int(2.5*2**30)
        self.assertIn('조기 중단',self.guard(1,0))
    def test_reader_closes_its_pipe(self):
        stream=io.StringIO('hello\n');out=queue.Queue()
        server.reader(None,stream,True,out)
        self.assertTrue(stream.closed)
        self.assertEqual(out.get(),'hello\n');self.assertIsNone(out.get())

    def test_dead_launcher_still_reaps_recorded_model_child(self):
        child=Mock();server.worker_children=[child]
        server.proc.poll.return_value=1
        with patch.object(server.psutil,'Process',side_effect=server.psutil.NoSuchProcess(42)),patch.object(server.psutil,'wait_procs',return_value=([child],[])) as wait:
            server.stop('test dead launcher')
        child.terminate.assert_called_once()
        self.assertEqual(server.worker_children,[])
        wait.assert_any_call([child],timeout=2)

    def test_dead_worker_is_cleaned_before_replacement(self):
        server.proc.poll.return_value=1
        with patch.object(server,'stop') as stop,patch.object(server,'memory',return_value={'available_gb':0}):
            with self.assertRaises(RuntimeError):server.launch()
        stop.assert_called_once()

if __name__=='__main__':unittest.main(verbosity=2)
