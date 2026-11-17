import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
import api_credentials,server

class PersistentApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(server.app)
        self.key=api_credentials.load_api_key()
        self.headers={'Authorization':'Bearer '+self.key}
    def test_missing_key(self):
        r=self.client.get('/api/v1/status');self.assertEqual(r.status_code,401);self.assertEqual(r.headers['www-authenticate'],'Bearer')
    def test_wrong_key(self):
        self.assertEqual(self.client.get('/api/v1/status',headers={'Authorization':'Bearer wrong'}).status_code,401)
    def test_valid_key(self):
        self.assertEqual(self.client.get('/api/v1/status',headers=self.headers).status_code,200)
    def test_foreign_origin(self):
        self.assertEqual(self.client.get('/api/v1/status',headers={**self.headers,'Origin':'https://example.com'}).status_code,403)
    def test_chat_requires_key(self):
        payload={'messages':[{'role':'user','content':'hello'}]}
        self.assertEqual(self.client.post('/api/v1/chat/stream',json=payload).status_code,401)
    def test_chat_delegates_to_existing_engine(self):
        async def fake(req):return StreamingResponse(iter(['{"token":"OK"}\n','{"done":true}\n']),media_type='application/x-ndjson')
        with patch.object(server,'stream',side_effect=fake):
            r=self.client.post('/api/v1/chat/stream',headers=self.headers,json={'messages':[{'role':'user','content':'hello'}]})
        self.assertEqual(r.status_code,200);self.assertIn('"done":true',r.text)
    def test_key_not_exposed(self):
        self.assertNotIn(self.key,self.client.get('/api/capabilities').text)
        self.assertEqual(self.client.get('/.secrets/api-key.txt').status_code,404)
    def test_persisted_file_reused(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(api_credentials,'KEY_FILE',Path(temp)/'secrets/api-key.txt'):
            a=api_credentials.load_api_key();b=api_credentials.load_api_key()
            self.assertEqual(a,b);self.assertTrue(a.startswith('nb_live_'))

if __name__=='__main__':unittest.main(verbosity=2)
