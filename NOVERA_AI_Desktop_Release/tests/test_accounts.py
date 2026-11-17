import json,os,secrets,sys,tempfile,threading,unittest,urllib.error,urllib.parse,urllib.request,time
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from local_accounts import Accounts,password_hash
from social_login import Settings,SocialLogin
import desktop


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'assets').mkdir();self.password=secrets.token_urlsafe(20)
        seed=self.root/'assets/developer-account.json';seed.write_text(json.dumps({'login':'soo_dev','password_hash':password_hash(self.password)}))
        self.accounts=Accounts(self.root,seed)

    def bridge(self):
        controller=Mock();controller.lock=threading.Lock()
        controller.bootstrap.side_effect=lambda:{'history':[{'id':'legacy','messages':[]}],'settings':{},'models':[],'adapters':[]}
        with patch.object(desktop,'DATA',self.root),patch.object(desktop,'BUNDLE',self.root):bridge=desktop.Bridge(controller)
        return bridge,controller

    def test_local_registration_login_and_privilege(self):
        bridge,c=self.bridge();password=secrets.token_urlsafe(16)
        self.assertTrue(bridge.register('new_user',password,password)['ok'])
        self.assertFalse(bridge.auth_status()['authenticated'])
        self.assertIn('error',bridge.register('NEW_USER',password,password))
        self.assertEqual(bridge.login('new_user',password)['user']['role'],'user')
        self.assertEqual(bridge.add_model()['code'],'developer_required')
        self.assertNotIn(password.encode(),bridge._accounts.database.read_bytes())
        bridge.logout();self.assertTrue(bridge.login('NEW_USER',password)['ok'])

    def test_registration_validation_and_reserved_names(self):
        password=secrets.token_urlsafe(16)
        for login,pw,confirmation in [('soo_dev',password,password),('admin',password,password),('../x',password,password),('ab',password,password),('valid_user','short','short'),('valid_user',password,'different')]:
            self.assertIn('error',self.accounts.register(login,pw,confirmation))

    def test_social_only_account_password_login_is_rejected(self):
        self.accounts.social('google',{'sub':'social_subject'})
        self.assertIn('error',self.accounts.login('google:social_subject','anything'))

    def test_no_model_or_history_access_before_login(self):
        bridge,c=self.bridge()
        self.assertFalse(bridge.bootstrap()['authenticated'])
        for action in [lambda:bridge.chat([]),lambda:bridge.image('test'),lambda:bridge.configure({}),lambda:bridge.save_history([]),bridge.logs,bridge.add_model,bridge.sync_web]:
            self.assertEqual(action()['code'],'login_required')
        c.chat.assert_not_called();c.bootstrap.assert_not_called()

    def test_developer_hash_and_role(self):
        bridge,c=self.bridge();self.assertIn('error',bridge.login('soo_dev','wrong'))
        self.assertEqual(bridge.login('soo_dev',self.password)['user']['role'],'developer')
        c.logs.return_value='local log';self.assertEqual(bridge.logs(),'local log')
        raw=self.accounts.database.read_bytes();self.assertNotIn(self.password.encode(),raw)

    def test_social_display_name_cannot_grant_developer_role(self):
        bridge,c=self.bridge();bridge._social_identity('google',{'sub':'subject1','email':'soo_dev@example.com','name':'soo_dev','email_verified':True})
        self.assertEqual(bridge.auth_status()['user']['role'],'user')
        self.assertEqual(bridge.add_model()['code'],'developer_required')
        self.assertEqual(bridge.sync_web()['code'],'developer_required')
        self.assertEqual(bridge.configure({'role':'developer','mode':'cpu'})['code'],'developer_required')
        c.configure.return_value={'ok':True};self.assertTrue(bridge.configure({'mode':'cpu'})['ok'])

    def test_identity_and_history_are_isolated(self):
        bridge,c=self.bridge();bridge._social_identity('google',{'sub':'g1','email':'same@example.com'})
        first=bridge._user['id'];self.assertEqual(bridge.bootstrap()['history'],[])
        bridge.save_history([{'id':'private','messages':[]}]);bridge.logout()
        self.assertFalse(bridge.auth_status()['authenticated'])
        bridge._social_identity('naver',{'id':'n1','email':'same@example.com'})
        self.assertNotEqual(bridge._user['id'],first);self.assertEqual(bridge.bootstrap()['history'],[])
        bridge._social_identity('google',{'sub':'g1','email':'different@example.com'})
        self.assertEqual(bridge.bootstrap()['history'][0]['id'],'private')

    def test_legacy_history_only_migrates_to_developer(self):
        bridge,c=self.bridge();bridge.login('soo_dev',self.password)
        self.assertEqual(bridge.bootstrap()['history'][0]['id'],'legacy')
        bridge.save_history([]);self.assertEqual(bridge.bootstrap()['history'],[])

    def test_repeated_failed_password_attempts_are_throttled(self):
        for _ in range(5):self.accounts.login('soo_dev','bad')
        self.assertIn('잠시 후',self.accounts.login('soo_dev',self.password)['error'])

    def test_secret_is_windows_encrypted_and_not_returned(self):
        settings=Settings(self.root);secret=secrets.token_urlsafe(30)
        settings.save('google','test.apps.googleusercontent.com',secret)
        self.assertNotIn(secret.encode(),settings.path.read_bytes())
        self.assertEqual(settings.read()['google']['client_secret'],secret)
        self.assertNotIn(secret,json.dumps(settings.public()))

    def test_missing_provider_configuration_does_not_open_browser(self):
        social=SocialLogin(Settings(self.root),Mock())
        with patch('social_login.webbrowser.open') as browser:
            self.assertEqual(social.start('google')['code'],'provider_not_configured');browser.assert_not_called()

    def test_google_pkce_state_and_callback_identity_flow(self):
        from authlib.integrations.requests_client import OAuth2Session
        settings=Settings(self.root);settings.save('google','test.apps.googleusercontent.com','fixture-secret')
        identity=Mock();social=SocialLogin(settings,identity);sessions=[]
        def factory(*args,**kwargs):
            client=OAuth2Session(*args,**kwargs)
            client.fetch_token=Mock(return_value={'access_token':'fixture-token','token_type':'Bearer'})
            response=Mock();response.json.return_value={'sub':'google-sub','email':'a@example.com','email_verified':True}
            client.get=Mock(return_value=response);sessions.append(client);return client
        with patch('authlib.integrations.requests_client.OAuth2Session',side_effect=factory),patch('social_login.webbrowser.open',return_value=True) as browser:
            self.assertTrue(social.start('google')['ok'])
            params=urllib.parse.parse_qs(urllib.parse.urlsplit(browser.call_args.args[0]).query)
            self.assertEqual(params['code_challenge_method'],['S256'])
            redirect=params['redirect_uri'][0];self.assertTrue(redirect.startswith('http://127.0.0.1:'))
            with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(redirect+'?code=fixture&state=wrong')
            self.assertEqual(failure.exception.code,400);identity.assert_not_called()
            with urllib.request.urlopen(redirect+'?'+urllib.parse.urlencode({'code':'fixture','state':params['state'][0]})) as response:self.assertEqual(response.status,200)
            for _ in range(50):
                if not social.status()['pending_provider']:break
                time.sleep(.02)
            identity.assert_called_once_with('google',{'sub':'google-sub','email':'a@example.com','email_verified':True})
            self.assertIn('code_verifier',sessions[0].fetch_token.call_args.kwargs)
            self.assertIsNone(social.status()['error'])

    def test_naver_callback_passes_state_and_accepts_only_provider_identity(self):
        from authlib.integrations.requests_client import OAuth2Session
        import social_login
        settings=Settings(self.root);settings.save('naver','fixture-client','fixture-secret')
        identity=Mock();social=SocialLogin(settings,identity);sessions=[]
        def factory(*args,**kwargs):
            client=OAuth2Session(*args,**kwargs)
            client.fetch_token=Mock(return_value={'access_token':'fixture-token','token_type':'bearer'})
            response=Mock();response.json.return_value={'resultcode':'00','response':{'id':'naver-sub','name':'fixture'}}
            client.get=Mock(return_value=response);sessions.append(client);return client
        definition={**social_login.PROVIDERS['naver'],'port':0}
        with patch.dict(social_login.PROVIDERS,{'naver':definition}),patch('authlib.integrations.requests_client.OAuth2Session',side_effect=factory),patch('social_login.webbrowser.open',return_value=True) as browser:
            self.assertTrue(social.start('naver')['ok'])
            params=urllib.parse.parse_qs(urllib.parse.urlsplit(browser.call_args.args[0]).query)
            self.assertNotIn('code_challenge',params)
            with urllib.request.urlopen(params['redirect_uri'][0]+'?'+urllib.parse.urlencode({'code':'fixture','state':params['state'][0]})) as response:self.assertEqual(response.status,200)
            for _ in range(50):
                if not social.status()['pending_provider']:break
                time.sleep(.02)
            identity.assert_called_once_with('naver',{'id':'naver-sub','name':'fixture'})
            self.assertEqual(sessions[0].fetch_token.call_args.kwargs['state'],params['state'][0])

    def test_cancelled_browser_login_never_creates_an_identity(self):
        settings=Settings(self.root);settings.save('google','test.apps.googleusercontent.com','fixture-secret')
        identity=Mock();social=SocialLogin(settings,identity)
        with patch('social_login.webbrowser.open',return_value=True):
            self.assertTrue(social.start('google')['ok']);social.cancel()
        self.assertIsNone(social.status()['pending_provider']);identity.assert_not_called()


if __name__=='__main__':unittest.main()
