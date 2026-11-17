import unittest
from engine import Message
from conversation_router import domain
from context_budget import compact_history
from assistant_tools import AssistantRequest, enrich_request, clarification_reply


class QwenContextRegressions(unittest.TestCase):
    def test_followup_is_not_intercepted_as_unknown_noun(self):
        messages=[{'role':'user','content':'Python 함수를 작성해줘'},
                  {'role':'assistant','content':'def f(x): return x'},
                  {'role':'user','content':'고쳐줘'}]
        self.assertIsNone(clarification_reply(messages,'고쳐줘'))
        prepared, metadata=enrich_request(AssistantRequest(messages=messages,enhance=True,skill='coding'))
        self.assertNotIn('direct_reply',metadata)
        self.assertNotIn('사용자가 단어만 입력했습니다',prepared.messages[0].content)

    def test_answer_to_prior_question_is_not_given_dictionary_instructions(self):
        messages=[{'role':'user','content':'여행 계획을 세워줘'},
                  {'role':'assistant','content':'어느 도시인가요?'},
                  {'role':'user','content':'서울'}]
        prepared, metadata=enrich_request(AssistantRequest(messages=messages,enhance=True))
        self.assertNotIn('direct_reply',metadata)
        self.assertNotIn('사용자가 단어만 입력했습니다',prepared.messages[0].content)

    def test_short_coding_followup_keeps_domain(self):
        self.assertEqual(domain([Message(role='user', content='Python 함수를 작성해줘'),
                                 Message(role='assistant', content='코드입니다.'),
                                 Message(role='user', content='고쳐줘')]), 'coding')

    def test_explicit_new_language_task_wins(self):
        self.assertEqual(domain([Message(role='user', content='Python 함수를 작성해줘'),
                                 Message(role='user', content='이 문장을 고쳐줘')]), 'language')

    def test_unrelated_topic_does_not_inherit_coding(self):
        self.assertEqual(domain([Message(role='user', content='Python 함수'),
                                 Message(role='user', content='오늘 날씨는?')]), 'general')

    def history(self, code):
        messages = [{'role':'user','content':'함수를 작성해줘'}, {'role':'assistant','content':code}]
        for i in range(8):
            messages += [{'role':'user','content':'다른 이야기 ' + str(i)},
                         {'role':'assistant','content':'설명 ' + '가'*300}]
        messages.append({'role':'user','content':'아까 apply_tax 함수를 수정해줘'})
        return messages

    def test_named_older_function_is_retained(self):
        code = '```python\ndef apply_tax(x):\n    return x + 10\n```'
        kept, _, budget = compact_history(self.history(code))
        self.assertTrue(budget['reference_pinned'])
        self.assertIn(code, [m['content'] for m in kept])
        self.assertLessEqual(budget['kept_chars'], 4800)

    def test_older_user_fact_keeps_latest_correction(self):
        messages=[{'role':'user','content':'프로젝트 이름은 NOVA야'},
                  {'role':'assistant','content':'알겠습니다'},
                  {'role':'user','content':'프로젝트 이름을 VIONA로 바꿀게'},
                  {'role':'assistant','content':'알겠습니다'}]
        for i in range(8):
            messages += [{'role':'user','content':f'다른 이야기 {i}'},
                         {'role':'assistant','content':'설명 '*120}]
        messages.append({'role':'user','content':'아까 프로젝트 이름이 뭐였지?'})
        kept,_,budget=compact_history(messages)
        self.assertTrue(budget['reference_pinned'])
        self.assertIn('프로젝트 이름을 VIONA로 바꿀게',[m['content'] for m in kept])
        self.assertNotIn('프로젝트 이름은 NOVA야',[m['content'] for m in kept])

    def test_oversized_reference_requests_source_instead_of_inventing(self):
        kept, memory, budget = compact_history(self.history('def apply_tax(x):\n' + '# comment\n'*1000))
        self.assertTrue(budget['reference_missing'])
        self.assertIn('원문을 요청', memory)


if __name__ == '__main__':
    unittest.main()
