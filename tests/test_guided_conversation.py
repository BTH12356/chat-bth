import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.guided_conversation import GuidedAnswer, GuidedConversationEngine


class GuidedConversationTests(unittest.TestCase):
    def setUp(self):
        self.engine = GuidedConversationEngine()

    def test_asks_one_question_and_exposes_reason(self):
        state = self.engine.start("internal_dashboard.v1", "session-1234", {"project_name": "Hermes"})
        self.assertEqual(state.status, "collecting")
        self.assertEqual(state.question.field_id, "project_name")
        self.assertTrue(state.question.reason)

    def test_invalid_answer_returns_clarification_without_mutating_values(self):
        state = self.engine.start("internal_dashboard.v1", "session-1234")
        state = self.engine.answer(state, GuidedAnswer(field_id="project_name", value="Hermes"))
        invalid = self.engine.answer(state, GuidedAnswer(field_id="project_type", value="website"))
        self.assertTrue(invalid.question.clarification)
        self.assertNotIn("project_type", invalid.values)

    def test_rules_reveal_follow_up_questions_and_review(self):
        state = self.engine.start("internal_dashboard.v1", "session-1234")
        answers = [
            ("project_name", "Hermes"), ("project_type", "internal_dashboard"),
            ("modules", ["worker_monitor", "ai_assistant"]), ("network_scope", "internet"),
            ("auth_enabled", True), ("ai_assistant", True),
            ("ai_capabilities", ["log_analysis"]), ("ai_autonomy", "approval_required"),
            ("https_required", True), ("allowed_origins", "https://example.com"),
            ("theme", "windows_xp.v1"), ("density", "compact"), ("language", ["th"]),
        ]
        for field_id, value in answers:
            state = self.engine.answer(state, GuidedAnswer(field_id=field_id, value=value))
        self.assertEqual(state.status, "review")
        self.assertEqual(self.engine.confirm(state).status, "confirmed")

    def test_schema_artifact_is_present(self):
        path = Path(__file__).parents[1] / "bth_create" / "schemas" / "hermes.guided-conversation.v1.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["$id"], "hermes.guided-conversation/v1")

    def test_website_empty_required_multi_select_is_clarified_before_review(self):
        state = self.engine.start("website_standard.v1", "session-website-1", {"project_name": "Hermes"})
        state = self.engine.answer(state, GuidedAnswer(field_id="project_name", value="Hermes"))
        state = self.engine.answer(state, GuidedAnswer(field_id="blueprint_id", value="website.landing.v1"))
        state = self.engine.answer(state, GuidedAnswer(field_id="tabs", value=[]))
        self.assertEqual(state.status, "collecting")
        self.assertEqual(state.question.field_id, "tabs")
        self.assertTrue(state.question.clarification)

    def test_website_tabs_must_be_a_clean_unique_list(self):
        state = self.engine.start("website_standard.v1", "session-website-tabs", {"project_name": "Hermes"})
        state = self.engine.answer(state, GuidedAnswer(field_id="project_name", value="Hermes"))
        state = self.engine.answer(state, GuidedAnswer(field_id="blueprint_id", value="website.landing.v1"))
        for invalid in ("home,about", ["หน้าหลัก", "หน้าหลัก"], [" "]):
            result = self.engine.answer(state, GuidedAnswer(field_id="tabs", value=invalid))
            self.assertEqual(result.question.field_id, "tabs")
            self.assertTrue(result.clarification)

    def test_rejects_answer_for_a_field_that_is_not_current(self):
        state = self.engine.start("website_standard.v1", "session-website-2", {"project_name": "Hermes"})
        with self.assertRaisesRegex(ValueError, "current guided field"):
            self.engine.answer(state, GuidedAnswer(field_id="language", value=["th"]))

    def test_website_cross_field_error_returns_to_correct_question(self):
        state = self.engine.start("website_standard.v1", "session-website-3", {"project_name": "Hermes"})
        answers = [
            ("project_name", "Hermes"), ("blueprint_id", "website.landing.v1"),
            ("tabs", ["หน้าหลัก"]), ("color_tone", "blue"),
            ("network_scope", "internet"), ("auth_enabled", False), ("density", "comfortable"),
            ("language", ["th"]), ("content_needed", False),
        ]
        for field_id, value in answers:
            state = self.engine.answer(state, GuidedAnswer(field_id=field_id, value=value))
        self.assertEqual(state.status, "collecting")
        self.assertEqual(state.question.field_id, "auth_enabled")
        self.assertIn("Authentication", state.clarification)

    def test_page_types_are_selected_automatically_from_navigation(self):
        state = self.engine.start("website_standard.v1", "session-website-types", {"project_name": "Hermes"})
        state = self.engine.answer(state, GuidedAnswer(field_id="project_name", value="Hermes"))
        state = self.engine.answer(state, GuidedAnswer(field_id="blueprint_id", value="website.landing.v1"))
        state = self.engine.answer(state, GuidedAnswer(field_id="tabs", value=["หน้าหลัก", "เกี่ยวกับเรา"]))
        self.assertEqual(state.values["page_types"], [])
        self.assertIn("page_types", state.asked)
        self.assertEqual(state.question.field_id, "color_tone")

    def test_confirmation_requires_review_and_summary_can_be_revised(self):
        state = self.engine.start("website_standard.v1", "session-website-4", {"project_name": "Hermes"})
        with self.assertRaisesRegex(ValueError, "reach review"):
            self.engine.confirm(state)
        answers = [
            ("project_name", "Hermes"), ("blueprint_id", "website.landing.v1"),
            ("tabs", ["หน้าหลัก"]), ("color_tone", "blue"),
            ("network_scope", "local"), ("auth_enabled", False), ("density", "comfortable"), ("language", ["th"]), ("content_needed", False),
        ]
        for field_id, value in answers:
            state = self.engine.answer(state, GuidedAnswer(field_id=field_id, value=value))
        self.assertEqual(state.status, "review")
        revised = self.engine.revise(state, "tabs")
        self.assertEqual(revised.status, "collecting")
        self.assertEqual(revised.question.field_id, "tabs")

    def test_thai_chat_answers_choose_form_options_and_keep_page_types_automatic(self):
        state = self.engine.start("website_standard.v1", "session-thai-chat", {"project_name": "Hermes"})
        state = self.engine.answer_text(state, "เว็บไซต์ร้านขายสินค้าออนไลน์")
        self.assertEqual(state.question.field_id, "blueprint_id")
        state = self.engine.answer_text(state, "ร้านขายสินค้าออนไลน์")
        self.assertEqual(state.values["blueprint_id"], "website.retail.v1")
        state = self.engine.answer_text(state, "หน้าหลัก, สินค้า, ติดต่อ")
        self.assertEqual(state.values["tabs"], ["หน้าหลัก", "สินค้า", "ติดต่อ"])
        self.assertIn("page_types", state.asked)
        self.assertEqual(state.values["page_types"], [])
        state = self.engine.answer_text(state, "อบอุ่น")
        self.assertEqual(state.values["color_tone"], "orange")
        state = self.engine.answer_text(state, "ให้คนทั่วไปดูผ่านอินเทอร์เน็ต")
        self.assertEqual(state.values["network_scope"], "internet")
        state = self.engine.answer_text(state, "ใช่")
        state = self.engine.answer_text(state, "โปร่ง อ่านง่าย")
        state = self.engine.answer_text(state, "ไทยและอังกฤษ")
        state = self.engine.answer_text(state, "ใช่")
        state = self.engine.answer_text(state, "ร้านขายสินค้าเพื่อสุขภาพจากผู้ผลิตในท้องถิ่น")
        state = self.engine.answer_text(state, "สินค้าออร์แกนิกและชุดของขวัญ")
        state = self.engine.answer_text(state, "คนรักสุขภาพ")
        state = self.engine.answer_text(state, "โทร 02-123-4567")
        self.assertEqual(state.status, "review")
        self.assertEqual(state.values["language"], ["th", "en"])

    def test_thai_library_intent_prefers_library_blueprint(self):
        state = self.engine.start("website_standard.v1", "session-thai-library", {"project_name": "ห้องสมุด BTH AI"})
        state = self.engine.answer_text(state, "ห้องสมุด BTH AI")
        state = self.engine.answer_text(state, "ห้องสมุดความรู้สำหรับทีม")
        self.assertEqual(state.values["blueprint_id"], "catalog.library.v1")


if __name__ == "__main__":
    unittest.main()
