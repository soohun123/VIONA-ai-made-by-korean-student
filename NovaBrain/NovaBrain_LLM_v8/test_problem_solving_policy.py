"""Prompt integration checks; no model or external services required."""
import unittest
from assistant_tools import AssistantRequest, enrich_request


class ProblemSolvingPolicyTests(unittest.TestCase):
    def prepare(self,text,**kwargs):
        return enrich_request(AssistantRequest(messages=[{'role':'user','content':text}],
                              enhance=True,search_mode='off',**kwargs))

    def test_code_explanation_does_not_force_implementation(self):
        prepared,meta=self.prepare('분석해줘: 이 Python 함수는 왜 느린가요?')
        self.assertEqual(meta['skill'],'coding')
        system=prepared.messages[0].content
        self.assertNotIn('Return only the requested implementation',system)
        self.assertIn('근거 없이 원인을 확정하지',system)
        self.assertFalse(prepared.code_only)

    def test_code_only_contract_and_sampling_are_preserved(self):
        prepared,_=self.prepare('Python 함수 f(x)를 만들어줘. 코드만 출력해.',temperature=0,max_tokens=256)
        self.assertTrue(prepared.code_only)
        self.assertEqual(prepared.temperature,0)
        self.assertEqual(prepared.max_tokens,256)
        self.assertEqual(prepared.repeat_penalty,1)
        self.assertEqual(prepared.frequency_penalty,0)

    def test_creative_request_preserves_requested_count(self):
        text='예산 0원으로 가능한 전시 아이디어 3개 제안해줘'
        prepared,_=self.prepare(text)
        self.assertEqual(prepared.messages[-1].content,text)
        self.assertIn('요청한 개수와 형식을 지키고',prepared.messages[0].content)

    def test_definition_does_not_trigger_creative_brief(self):
        prepared,_=self.prepare('창의성이 무엇인지 설명해줘')
        self.assertNotIn('창작 요청에서는',prepared.messages[0].content)

    def test_plain_conversation_has_no_problem_solving_checklist(self):
        prepared,_=self.prepare('안녕하세요. 좋은 아침이에요.')
        self.assertNotIn('문제 해결에서는',prepared.messages[0].content)

    def test_raw_evaluation_request_is_untouched(self):
        req=AssistantRequest(messages=[{'role':'user','content':'Python 코드 분석해줘'}],
                             enhance=False,max_tokens=10000,temperature=0)
        prepared,meta=enrich_request(req)
        self.assertIsNone(meta)
        self.assertEqual(prepared.messages,req.messages)
        self.assertEqual(prepared.max_tokens,10000)


if __name__=='__main__':unittest.main()
