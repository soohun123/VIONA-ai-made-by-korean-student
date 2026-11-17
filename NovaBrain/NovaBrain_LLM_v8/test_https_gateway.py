import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import https_gateway as g
from api_credentials import load_api_key

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.origin='https://viona-test.trycloudflare.com'
        self.mock=patch.object(g,'network_settings',return_value={'public_url':self.origin,'cors_origins':[self.origin]});self.mock.start()
        self.client=TestClient(g.app,base_url=self.origin)
    def tearDown(self):self.client.close();self.mock.stop()
    def test_login_page_without_auth(self):
        r=self.client.get('/');self.assertEqual(r.status_code,200);self.assertIn('VIONA',r.text);self.assertNotIn(load_api_key(),r.text)
        self.assertEqual(r.headers['referrer-policy'],'same-origin')
    def test_unauthenticated_api_denied(self):self.assertEqual(self.client.get('/status').status_code,401)
    def test_bad_login(self):self.assertEqual(self.client.post('/login',data={'key':'incorrect'}).status_code,401)
    def login(self):
        r=self.client.post('/login',data={'key':load_api_key()},follow_redirects=False)
        self.assertEqual(r.status_code,303);cookie=r.headers['set-cookie'].lower()
        for flag in ('secure','httponly','samesite=strict'):self.assertIn(flag,cookie)
    def test_login_cookie_and_remote_admin_denied(self):
        self.login();r=self.client.post('/api/desktop',json={'operation':'windows'})
        self.assertEqual(r.status_code,403)
    def test_remote_key_file_denied(self):
        self.login();self.assertEqual(self.client.get('/.secrets/api-key.txt').status_code,403)
    def test_origin_allowlist(self):
        headers={'Origin':self.origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Authorization,Content-Type'}
        r=self.client.options('/api/v1/chat/stream',headers=headers)
        self.assertEqual(r.status_code,200);self.assertEqual(r.headers['access-control-allow-origin'],self.origin)
        r=self.client.options('/api/v1/chat/stream',headers={**headers,'Origin':'https://evil.example'})
        self.assertGreaterEqual(r.status_code,400);self.assertNotIn('access-control-allow-origin',r.headers)
    def test_foreign_origin_and_host_denied(self):
        self.assertEqual(self.client.post('/login',headers={'Origin':'https://evil.example'},data={'key':load_api_key()}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,403)
    def test_invalid_cookie_denied(self):
        self.client.cookies.set(g.COOKIE,'1234.invalid')
        self.assertEqual(self.client.get('/status').status_code,401)

if __name__=='__main__':unittest.main(verbosity=2)
