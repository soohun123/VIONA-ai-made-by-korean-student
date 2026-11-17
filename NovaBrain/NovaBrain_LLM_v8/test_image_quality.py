import unittest
from image_quality import simple_visual_translation, visual_subject
from content_filter import image_reason


class ImagePromptRegressions(unittest.TestCase):
    def test_bring_is_not_part_of_visual_prompt(self):
        self.assertEqual(simple_visual_translation('비행기 사진을 가져와'), 'a photograph of an airplane')

    def test_short_draw_request_does_not_force_pencil_sketch(self):
        self.assertEqual(simple_visual_translation('비행기를 그려줘'), 'an airplane')

    def test_explicit_illustration_is_preserved(self):
        self.assertEqual(simple_visual_translation('자동차 그림을 만들어줘'), 'an illustration of a car')

    def test_counts_and_colors_go_to_translator_intact(self):
        self.assertIsNone(simple_visual_translation('빨간 비행기 두 대를 그려줘'))
        self.assertEqual(visual_subject('빨간 비행기 두 대를 그려줘'), '빨간 비행기 두 대를')

    def test_subject_action_is_not_removed(self):
        self.assertEqual(visual_subject('공을 가져오는 강아지'), '공을 가져오는 강아지')

    def test_high_sexual_score_remains_blocked(self):
        self.assertIsNotNone(image_reason({'sexual': .99, 'violence': 0}))

    def test_high_violence_score_remains_blocked(self):
        self.assertIsNotNone(image_reason({'sexual': 0, 'violence': .99}))


if __name__ == '__main__':
    unittest.main()
