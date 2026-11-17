import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient
from plugin_registry import Registry,Manifest
from context_budget import compact_history,compact_desktop
from desktop_bridge import DesktopBridge
import server
import assistant_tools as tools

class PluginBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.registry=Registry(Path(self.temp.name)/'plugins.json')
    def test_manifest_does_not_accept_code_or_unknown_tools(self):
        for extra in ({'entrypoint':'evil.py'},{'capabilities':['shell.exec']},{'id':'../outside'}):
            with self.assertRaises(ValidationError):Manifest(**{'id':'my-plugin','name':'test',**extra})
    def test_install_export_duplicate_does_not_replace(self):
        self.registry.install(Manifest(id='my-plugin',name='original'))
        with self.assertRaises(ValueError):self.registry.install(Manifest(id='my-plugin',name='overwrite'))
        self.assertEqual(self.registry.get('my-plugin')['name'],'original')
        self.assertEqual(Registry(self.registry.path).get('my-plugin')['name'],'original')
    def test_disable_and_remove_preserve_backup(self):
        self.registry.install(Manifest(id='my-plugin',name='test',capabilities=['desktop.read']))
        self.registry.enable('my-plugin',False)
        with self.assertRaises(PermissionError):self.registry.require('my-plugin','desktop.read')
        self.registry.remove('my-plugin')
        self.assertTrue(list((self.registry.path.parent/'plugin-backups').glob('*.json')))
        with self.assertRaises(ValueError):self.registry.get('my-plugin')
    def test_builtin_cannot_be_overwritten_or_removed(self):
        with self.assertRaises(ValueError):self.registry.install(Manifest(id='computer-use',name='bad'))
        with self.assertRaises(ValueError):self.registry.remove('computer-use')
    def test_missing_action_permission_blocks_tool(self):
        self.registry.install(Manifest(id='read-only',name='read',capabilities=['desktop.read']))
        with patch.object(server,'registry',self.registry),patch.object(server.desktop,'action') as action:
            client=TestClient(server.app)
            response=client.post('/api/desktop',json={'operation':'click','plugin_id':'read-only','ref':'@x:e1','confirmed':True},headers={'x-novabrain-token':server.TOOL_TOKEN})
            self.assertEqual(response.status_code,403);action.assert_not_called()
    def test_plugin_mutations_need_token_and_export_is_declarative(self):
        with patch.object(server,'registry',self.registry):
            client=TestClient(server.app);payload={'id':'via-api','name':'test'}
            self.assertEqual(client.post('/api/plugins',json=payload).status_code,403)
            headers={'x-novabrain-token':server.TOOL_TOKEN}
            self.assertEqual(client.post('/api/plugins',json=payload,headers=headers).status_code,200)
            exported=client.get('/api/plugins/via-api/manifest').json()
            self.assertNotIn('enabled',exported);self.assertEqual(Manifest(**exported).id,'via-api')
    def test_context_reduction_keeps_latest_exchange_and_old_user_memory(self):
        messages=[]
        for i in range(20):
            messages += [{'role':'user','content':('내 프로젝트 이름은 시드입니다.' if i==0 else '질문'+str(i))+('x'*500)}, {'role':'assistant','content':'답변'+str(i)+'y'*1000}]
        messages.append({'role':'user','content':'방금 답변을 바탕으로 고쳐 줘.'})
        kept,memory,stats=compact_history(messages,'economy')
        self.assertEqual(kept[-1],messages[-1]);self.assertIn(messages[-2],kept);self.assertIn('시드',memory)
        self.assertLess(stats['kept_chars']+len(memory),stats['original_chars']*.3)
        self.assertEqual(kept[0]['role'],'user')
    def test_latest_question_is_never_silently_truncated(self):
        text='a'*20000;kept,_,_=compact_history([{'role':'user','content':text}])
        self.assertEqual(kept[0]['content'],text)
    def test_pinned_memory_survives_in_full_mode(self):
        _,memory,_=compact_history([{'role':'user','content':'질문'}],'full','환경은 Windows 11')
        self.assertIn('Windows 11',memory)
    def test_desktop_context_reduced_without_huge_field_values(self):
        original=json.dumps([{'name':'button'+str(i),'role':'button','ref_id':'@s:e'+str(i),'value':'SECRET'*1000} for i in range(80)])
        compact=compact_desktop(original)
        self.assertLessEqual(len(compact),1200);self.assertNotIn('SECRET',compact)
    def test_enabled_plugin_instructions_and_output_limit(self):
        self.registry.install(Manifest(id='short-code',name='short',instructions='ONLY_NEEDED_CHANGES',max_response_tokens=256))
        request=tools.AssistantRequest(messages=[{'role':'user','content':'파이썬 더하기 함수를 작성해 줘.'}],enhance=True,plugin_id='short-code',max_tokens=2048)
        with patch.object(tools,'registry',self.registry):prepared,meta=tools.enrich_request(request)
        self.assertIn('ONLY_NEEDED_CHANGES',prepared.messages[0].content);self.assertEqual(prepared.max_tokens,256)
        self.assertEqual(meta['budget']['max_output_tokens'],256)
    def test_snapshot_cache_prevents_duplicate_full_read(self):
        bridge=DesktopBridge();fixture={'ok':True,'data':{'tree':{'role':'window','children':[{'ref_id':'@s:e1','role':'button','name':'검증','available_actions':['Click']}]}}}
        with patch.object(bridge,'activate',return_value=None),patch.object(bridge,'run',return_value=fixture) as run:
            first=bridge.snapshot('w-1');second=bridge.snapshot('w-1')
            self.assertTrue(first['ok']);self.assertTrue(second['data']['cached']);self.assertEqual(run.call_count,1)

if __name__=='__main__':unittest.main(verbosity=2)
