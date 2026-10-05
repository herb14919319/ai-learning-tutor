from __future__ import annotations

import json
import unittest
from pathlib import Path

import main
from skills.ipas_cybersecurity import IpasCybersecuritySkill
from skills.ipas_cybersecurity.review import verify_source


ROOT = Path(__file__).resolve().parents[1] / 'skills/ipas_cybersecurity'
PROCESSED = ROOT / 'knowledge/processed'


class ControlledPhysicalSecurityPilotTest(unittest.TestCase):
    def test_new_slice_uses_frozen_schema_and_canonical_pages(self):
        verify_source(PROCESSED)
        index = json.loads((PROCESSED / 'chapter_index.json').read_text(encoding='utf-8'))
        pilot = index[-1]
        self.assertEqual((pilot['chapter_id'], pilot['schema_file'], pilot['source_pages']),
                         ('I11-PHYS', 'learning_chunk_schema_v0_4.json', list(range(84, 91))))
        chunks = json.loads((PROCESSED / pilot['chunk_file']).read_text(encoding='utf-8'))
        self.assertEqual(len(chunks), 10)
        self.assertEqual({page for chunk in chunks for page in chunk['source_evidence']['source_pages']},
                         set(range(84, 91)))
        self.assertTrue(all(chunk['source_evidence']['source_file'] == pilot['source_file']
                            and chunk['teaching_interpretation']['review_status'] == 'pending_review'
                            for chunk in chunks))
        self.assertEqual(len({chunk['chunk_id'] for chunk in chunks}), len(chunks))

        # Owner review of this slice is ongoing: assets may move from pending_review to
        # reviewed, but the checked-in baseline keeps every Phase 6 asset visible.
        visible = {'pending_review', 'reviewed'}
        skill = IpasCybersecuritySkill()
        self.assertEqual(skill.get_course_info()['chapter_count'], 5)
        chapter = skill.get_chapter('I11-PHYS')
        self.assertIn(chapter['teaching_review_status'], visible)
        self.assertEqual(len(chapter['chunks']), 10)
        self.assertTrue(all(chunk['teaching_interpretation']['review_status'] in visible
                            for chunk in chapter['chunks']))
        self.assertEqual(len(skill.get_flashcards('I11-PHYS')), 12)
        self.assertEqual(len(skill.get_questions('I11-PHYS')), 12)
        self.assertTrue(all(card['review_status'] in visible
                            for card in skill.get_flashcards('I11-PHYS')))
        self.assertTrue(all(question['review_status'] in visible
                            and 'correct_answer' not in question and 'explanation' not in question
                            for question in skill.get_questions('I11-PHYS')))
        self.assertEqual(skill.get_chapter('I11-ASSET')['teaching_review_status'], 'reviewed')
        self.assertEqual([card['review_status'] for card in skill.get_flashcards('I11-ASSET')],
                         ['reviewed'] * 10)

    def test_new_web_quiz_and_tutor_retrieval(self):
        skill = IpasCybersecuritySkill()
        self.assertIn('I11-PHYS-010', skill.query_concept('機房空調')['chunk_id'])
        self.assertRegex(skill.answer('請說明周邊安全'), '審核狀態：(pending_review|reviewed)')
        self.assertIn('I11-PHYS-Q001', skill.answer('實體安全練習題'))
        with main.app.test_client() as client:
            html = client.get('/ipas/cybersecurity').get_data(as_text=True)
            self.assertIn('I11-PHYS-Q001', html)
            self.assertIn('5 個小主題', html)
            self.assertNotIn('"correct_answer"', html)
            self.assertNotIn('"explanation"', html)
            response = client.post('/api/ipas/cybersecurity/answer',
                                   json={'question_id': 'I11-PHYS-Q001', 'answer': 'A'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['correct'])
            self.assertEqual(response.json['source_references'][0]['source_pages'], [84])


if __name__ == '__main__':
    unittest.main()
