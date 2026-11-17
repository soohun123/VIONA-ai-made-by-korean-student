import unittest
from translation_checks import integrity_issues,visual_glossary,korean_glossary,explicit_translation
from image_quality import simple_visual_translation


class TranslationIntegrityTests(unittest.TestCase):
    def test_explicit_translation_route(self):
        self.assertEqual(explicit_translation('영어로 번역해줘: 빨간 자동차'),('en','빨간 자동차'))
    def test_how_to_translate_is_not_executed(self):
        self.assertIsNone(explicit_translation('영어로 번역하는 방법을 알려줘'))
    def test_runway_term(self):
        self.assertEqual(korean_glossary('airplane on the runway','도로 위 비행기'),'활주로 위 비행기')
    def test_number_loss_rejected(self):
        self.assertIn('Number missing: 737',integrity_issues('보잉 737','a Boeing airplane','en'))
    def test_count_loss_rejected(self):
        self.assertTrue(integrity_issues('자동차 두 대','a car','en'))
    def test_english_spelled_count_accepted(self):
        self.assertEqual(integrity_issues('빨간 자동차 두 대','two red cars','en'),[])
    def test_color_loss_rejected(self):
        self.assertTrue(integrity_issues('파란 자동차','a red car','en'))
    def test_negation_loss_rejected(self):
        self.assertTrue(integrity_issues('사람 없이','people at an airport','en'))
    def test_negation_kept(self):
        self.assertEqual(integrity_issues('사람 없이','an airport without people','en'),[])
    def test_side_view_glossary_uses_explicit_source(self):
        self.assertEqual(visual_glossary('에어버스 옆모습 사진','Airbus next door.'),'a photograph of Airbus side view')
    def test_glossary_does_not_change_actual_next_door(self):
        self.assertEqual(visual_glossary('옆집 자동차','car next door'),'car next door')
    def test_image_request_typo(self):
        self.assertEqual(simple_visual_translation('비행기 이미지만들어죠'),'an airplane')
    def test_ko_count_loss_rejected(self):
        self.assertTrue(integrity_issues('Two red cars','자동차','ko'))
    def test_ko_count_preserved(self):
        self.assertEqual(integrity_issues('Two cars','자동차 두 대','ko'),[])
    def test_repeated_fragment_rejected(self):
        self.assertTrue(integrity_issues('자동차','a car is parked outside '*4,'en'))


if __name__ == '__main__':unittest.main()
