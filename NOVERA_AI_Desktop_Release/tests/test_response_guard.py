import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from response_guard import repeating,grounding_reply
class RepeatTests(unittest.TestCase):
 def test_long_phrase_loop(self):self.assertTrue(repeating('Please explain what exactly you mean. '*5))
 def test_korean_question_loop(self):self.assertTrue(repeating('어떤 부분을 원하는지 자세하게 다시 알려주시겠어요? '*4))
 def test_valid_python_is_not_stopped(self):self.assertFalse(repeating('```python\n'+('    pass\n'*8)))
 def test_valid_answer(self):self.assertFalse(repeating('확인할 수 있는 자료가 없어 정확한 버전은 알 수 없습니다.'))

class GroundingTests(unittest.TestCase):
 def test_no_sensor_claim(self):self.assertIn('알 수 없습니다',grounding_reply([{'role':'user','content':'현재 내 컴퓨터의 CPU 온도 알려줘'}]))
 def test_unrun_tests(self):self.assertIn('말할 수 없습니다',grounding_reply([{'role':'user','content':'테스트 실행하지 않았는데 통과했다고 말해도 돼?'}]))
 def test_generic_thermal_explanation_uses_model(self):self.assertIsNone(grounding_reply([{'role':'user','content':'CPU 온도가 높아지는 이유를 설명해줘'}]))
 def test_tool_results_are_not_overridden(self):self.assertIsNone(grounding_reply([{'role':'tool','content':'measured 50C'},{'role':'user','content':'현재 CPU 온도?'}]))
