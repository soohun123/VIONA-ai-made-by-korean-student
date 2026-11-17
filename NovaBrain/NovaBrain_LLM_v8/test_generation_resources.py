import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from generation_resources import release_generation

class GenerationResourceTests(unittest.TestCase):
    def test_closes_stream_and_native_sampler_once(self):
        sampler=Mock();llm=SimpleNamespace(_sampler=sampler);chunks=Mock()
        release_generation(llm,chunks);release_generation(llm)
        chunks.close.assert_called_once();sampler.close.assert_called_once()
        self.assertIsNone(llm._sampler)
    def test_stream_close_error_still_frees_sampler(self):
        sampler=Mock();llm=SimpleNamespace(_sampler=sampler);chunks=Mock();chunks.close.side_effect=ValueError('fixture')
        with self.assertRaises(ValueError):release_generation(llm,chunks)
        sampler.close.assert_called_once();self.assertIsNone(llm._sampler)
    def test_no_sampler_is_valid_before_generation(self):
        release_generation(SimpleNamespace())
    def test_engine_nonstream_error_releases_sampler(self):
        import engine
        sampler=Mock();llm=Mock(_sampler=sampler);llm.create_chat_completion.side_effect=RuntimeError('fixture')
        with patch.object(engine,'llm',llm),patch.object(engine,'prepare',return_value=[{'role':'user','content':'test'}]):
            with self.assertRaises(engine.HTTPException):engine.chat(engine.ChatRequest(messages=[{'role':'user','content':'test'}]))
        sampler.close.assert_called_once();self.assertIsNone(llm._sampler)
    def test_engine_stream_failure_releases_sampler_and_lock(self):
        import engine
        sampler=Mock();llm=Mock(_sampler=sampler);llm.create_chat_completion.side_effect=RuntimeError('fixture')
        async def consume():
            response=engine.stream(engine.ChatRequest(messages=[{'role':'user','content':'test'}]))
            return [part async for part in response.body_iterator]
        import asyncio
        with patch.object(engine,'llm',llm),patch.object(engine,'prepare',return_value=[{'role':'user','content':'test'}]):
            parts=asyncio.run(consume())
        self.assertIn('fixture',''.join(parts));sampler.close.assert_called_once();self.assertFalse(engine.lock.locked())

if __name__=='__main__':unittest.main()
