"""Focused regressions: no model calls; candidate execution only in WASI."""
import unittest
from unittest.mock import patch

from coding_workflow import check_source, extract_source, repair_messages


class CodingValidationRegressions(unittest.TestCase):
    def test_literal_backticks_are_not_extra_code_blocks(self):
        reply = '```python\ndef render():\n    return "```example```"\n```'
        source = extract_source(reply)
        self.assertTrue(check_source(source)['syntax_valid'])

    def test_multiple_candidate_blocks_cannot_be_selected(self):
        source = extract_source('```python\nx = 1\n```\n```python\nx = 2\n```')
        self.assertFalse(check_source(source)['syntax_valid'])

    def test_ast_only_false_positive_is_rejected(self):
        result = check_source('return 1\n')
        self.assertFalse(result['syntax_valid'])
        self.assertIsNone(result['tests_passed'])

    def test_compilation_never_executes_candidate(self):
        with patch('builtins.print') as output:
            result = check_source('print("candidate must not execute")\n')
        output.assert_not_called()
        self.assertTrue(result['syntax_valid'])
        self.assertIsNone(result['tests_passed'])

    def test_repair_retains_contract_in_last_message(self):
        task = 'Keep the input unchanged and return a tuple.'
        messages = repair_messages(task, 'def f(x): return x', 'AssertionError')
        self.assertEqual(len(messages), 2)
        self.assertIn(task, messages[-1]['content'])
        self.assertIn('def f(x): return x', messages[-1]['content'])
        self.assertIn('AssertionError', messages[-1]['content'])

    def test_missing_entry_point_is_rejected(self):
        self.assertFalse(check_source('def other(): return 1\n', entry_point='wanted')['syntax_valid'])


class IsolatedDiagnosticsRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sandbox_eval import Sandbox
        cls.sandbox = Sandbox()

    def test_failed_check_exposes_check_line(self):
        result = check_source('def f(): return 1\n', self.sandbox,
                              'assert f() == 2', 'f')
        self.assertFalse(result['tests_passed'])
        self.assertIn('CHECK_LINE 1 assert f() == 2', result['output'])

    def test_success_requires_reaching_end_of_checks(self):
        good = check_source('def f(): return 1\n', self.sandbox, 'assert f() == 1', 'f')
        self.assertTrue(good['tests_passed'])
        early_exit = check_source('def f(): return 1\n', self.sandbox,
                                  'import sys\nsys.exit(0)', 'f')
        self.assertFalse(early_exit['tests_passed'])


if __name__ == '__main__':
    unittest.main()
