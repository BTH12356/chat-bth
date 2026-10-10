"""Tests for the Hybrid Form and deterministic Rule Engine."""

import unittest

from pydantic import ValidationError

from bth_create.form_engine import (
    FormDefinition,
    FormStore,
    MockAIInterview,
    RuleEngine,
    UnknownRequirement,
)


class FormEngineTests(unittest.TestCase):
    def setUp(self):
        self.definition = FormStore().get("internal_dashboard.v1")
        self.engine = RuleEngine()

    def test_static_defaults_are_available_without_rules(self):
        view = self.engine.evaluate(self.definition, {"project_name": "BTH Control Center"})
        self.assertEqual(view.values["project_name"], "BTH Control Center")
        self.assertEqual(view.values["network_scope"], "local")
        self.assertNotIn("ai_capabilities", view.visible_fields)
        self.assertNotIn("https_required", view.visible_fields)
        self.assertNotIn("ai_enabled_questions", view.fired_rules)

    def test_ai_rule_reveals_and_requires_ai_fields(self):
        view = self.engine.evaluate(self.definition, {"ai_assistant": True})
        self.assertIn("ai_capabilities", view.visible_fields)
        self.assertIn("ai_autonomy", view.visible_fields)
        self.assertIn("ai_capabilities", view.required_fields)
        self.assertIn("ai_enabled_questions", view.fired_rules)

    def test_network_rule_is_deterministic(self):
        local = self.engine.evaluate(self.definition, {"network_scope": "local"})
        internet = self.engine.evaluate(self.definition, {"network_scope": "internet"})
        self.assertNotIn("https_required", local.visible_fields)
        self.assertIn("https_required", internet.visible_fields)
        self.assertIn("allowed_origins", internet.visible_fields)
        self.assertIn("https_required", internet.required_fields)

    def test_unknown_form_values_are_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate(self.definition, {"not_a_field": True})

    def test_definition_rejects_unknown_rule_references(self):
        raw = self.definition.model_dump()
        raw["rules"][0]["when"][0]["field"] = "missing"
        with self.assertRaises(ValidationError):
            FormDefinition.model_validate(raw)

    def test_mock_ai_interview_only_returns_clarifying_questions(self):
        requirement = UnknownRequirement(text="Compare engineering documents to company standards")
        questions = MockAIInterview().questions_for(requirement)
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0].id, "goal")
        self.assertTrue(all(question.question for question in questions))


if __name__ == "__main__":
    unittest.main()
