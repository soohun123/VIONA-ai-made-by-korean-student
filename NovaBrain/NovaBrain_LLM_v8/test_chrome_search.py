import json,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
import server,chrome_search as search
from model_catalog import seal

class BrowserSearchTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(server.app);self.headers={'X-NovaBrain-Token':server.TOOL_TOKEN};server.cancel_event.clear()
    def test_positive_commands(self):
        for text in ['파이썬 문서 찾아줘','서울 날씨 검색해 줘','GPU 정보를 찾아주세요']:self.assertTrue(search.search_intent(text))
    def test_negative_and_meta_commands(self):
        for text in ['검색하지 마','그냥 설명해 줘','검색해줘를 입력하면 동작하는 기능을 만들어줘']:self.assertFalse(search.search_intent(text))
    def test_clean_query(self):
        self.assertEqual(search.clean_query('검색어:  Python   tutorial'),'Python tutorial')
    def test_api_requires_local_tool_token(self):
        self.assertEqual(self.client.post('/api/browser/search',json={'text':'파이썬 찾아줘'}).status_code,403)
    def test_public_gateway_cannot_operate_chrome(self):
        r=self.client.post('/api/browser/search',headers={**self.headers,'X-Viona-Public':seal()},json={'text':'파이썬 찾아줘'});self.assertEqual(r.status_code,403)
    def test_missing_subject_never_opens_chrome(self):
        with patch.object(search,'run_search') as run:
            r=self.client.post('/api/browser/search',headers=self.headers,json={'text':'찾아줘'})
        self.assertEqual(r.status_code,422);run.assert_not_called()
    def test_query_is_planned_before_browser_search(self):
        async def plan(req,request):
            self.assertEqual(req.interaction_mode,'chat');self.assertEqual(req.search_mode,'off')
            return StreamingResponse(iter(['{"token":"Python 공식 문서"}\n','{"done":true}\n']))
        with patch.object(server,'stream',side_effect=plan),patch.object(search,'run_search',return_value={'query':'Python 공식 문서','sources':[]}) as run:
            r=self.client.post('/api/browser/search',headers=self.headers,json={'text':'파이썬 공식 설명 찾아줘'})
        self.assertEqual(r.status_code,200);self.assertEqual(run.call_args.args[0],'Python 공식 문서')
    def test_filtered_request_never_opens_chrome(self):
        async def blocked(req,request):return StreamingResponse(iter(['{"token":"blocked"}\n','{"done":true,"metrics":{"response_origin":"content_filter"}}\n']))
        with patch.object(server,'stream',side_effect=blocked),patch.object(search,'run_search') as run:
            r=self.client.post('/api/browser/search',headers=self.headers,json={'text':'차단할 내용 찾아줘'})
        self.assertEqual(r.status_code,403);run.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
