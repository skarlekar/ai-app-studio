import json
import os
import unittest
from unittest.mock import patch

from gptapps.setup import SetupInterpreter
from gptapps.spec import analyze, from_chat_input
from test_framework import FakeClient, response


def interpretation(value=None, status="accept", message="Understood."):
    return response(json.dumps({"status": status, "value": value, "message": message}))


@patch.dict(os.environ, {"OPENAI_MODEL": "test-model", "OPENAI_SETUP_MODEL": "setup-model"})
class SetupTests(unittest.TestCase):
    def test_conversational_settings_produce_a_runnable_draft(self):
        replies = [
            ("name", "Call it Spanish Teacher", "Spanish Teacher"),
            ("description", "It helps me practise Spanish", "It helps me practise Spanish"),
            ("starters", "No conversation starters needed", []),
            ("tools", "Enable web search but no images or code", ["web_search"]),
            ("model", "Use the default model", None),
            ("knowledge_files", "I don't have any knowledge files", []),
            ("actions", "No actions are required", []),
        ]
        client = FakeClient(*(interpretation(value) for _, _, value in replies))
        setup = SetupInterpreter(client)
        draft = {"instructions": "  Teach Spanish.\nKeep these exact instructions.\n"}
        for field, text, expected in replies:
            result = setup.interpret(field, text)
            self.assertEqual(result["status"], "accept")
            self.assertEqual(result["value"], expected)
            draft[field] = result["value"]
        app = from_chat_input(draft)
        self.assertTrue(analyze(app)["runtime_ready"])
        self.assertEqual(app["instructions"], draft["instructions"])
        for payload in client.requests:
            self.assertEqual(payload["model"], "setup-model")
            self.assertFalse(payload["store"])
            self.assertNotIn("tools", payload)
            self.assertTrue(payload["text"]["format"]["strict"])

    def test_clarification_keeps_context_without_treating_it_as_instructions(self):
        question = "Do you have any knowledge files, or should the inventory be empty?"
        client = FakeClient(interpretation(status="clarify", message=question), interpretation([]))
        setup = SetupInterpreter(client)
        first = setup.interpret("knowledge_files", "I'm not sure")
        self.assertEqual(first["status"], "clarify")
        history = [{"role": "user", "content": "I'm not sure"}, {"role": "assistant", "content": question}]
        self.assertEqual(setup.interpret("knowledge_files", "I have none", history)["value"], [])
        payload = client.requests[-1]
        self.assertEqual(len(payload["input"]), 1)
        self.assertEqual(payload["input"][0]["role"], "user")
        context = json.loads(payload["input"][0]["content"])
        self.assertEqual(context["clarification_history"], history)
        self.assertEqual(context["reply"], "I have none")

    def test_instructions_and_action_schemas_are_preserved_without_model_calls(self):
        client = FakeClient()
        setup = SetupInterpreter(client)
        instructions = "  Follow the user's directions.\nDo not rewrite this.\n"
        self.assertEqual(setup.interpret("instructions", instructions)["value"], instructions)
        actions = [{"name": "Lookup", "auth_type": "none",
                    "schema": {"openapi": "3.1.0", "info": {"title": "Lookup", "version": "1.0"}, "paths": {}}}]
        for raw in (json.dumps(actions), "```json\n" + json.dumps(actions) + "\n```"):
            self.assertEqual(setup.interpret("actions", raw)["value"], actions)
        self.assertEqual(client.requests, [])

    def test_actual_file_names_still_require_bindings(self):
        setup = SetupInterpreter(FakeClient(interpretation(["none.pdf", "guide.pdf"])))
        files = setup.interpret("knowledge_files", "Use none.pdf and guide.pdf")["value"]
        app = from_chat_input({"name": "App", "instructions": "Help", "knowledge_files": files})
        self.assertIn("knowledge_unbound", {issue["code"] for issue in analyze(app)["issues"]})

    def test_model_output_is_validated_before_returning_it(self):
        cases = [("tools", ["unsupported"]), ("name", ""), ("model", []),
                 ("knowledge_files", "none"), ("starters", ["x" * 501])]
        for field, value in cases:
            with self.subTest(field=field), self.assertRaises(ValueError):
                SetupInterpreter(FakeClient(interpretation(value))).interpret(field, "Some reply")

    def test_model_cannot_invent_or_rewrite_action_definitions(self):
        actions = [{"name": "Invented", "auth_type": "none", "schema_json": '{"openapi":"3.1.0"}'}]
        setup = SetupInterpreter(FakeClient(interpretation(actions)))
        result = setup.interpret("actions", "I want to look up orders")
        self.assertEqual(result["status"], "clarify")
        self.assertIsNone(result["value"])

    def test_user_supplied_action_credentials_are_rejected(self):
        actions = [{"name": "Lookup", "auth_type": "api_key", "schema": {"openapi": "3.1.0"}, "api_key": "example"}]
        with self.assertRaisesRegex(ValueError, "no credential fields"):
            SetupInterpreter(FakeClient()).interpret("actions", json.dumps(actions))

    def test_creation_only_allowed_at_review(self):
        setup = SetupInterpreter(FakeClient(interpretation(status="create")))
        self.assertEqual(setup.interpret("review", "Looks good, go ahead")["status"], "create")
        with self.assertRaisesRegex(ValueError, "Invalid setup interpretation"):
            SetupInterpreter(FakeClient(interpretation(status="create"))).interpret("name", "Make an app")
        with self.assertRaisesRegex(ValueError, "explicit request"):
            SetupInterpreter(FakeClient(interpretation())).interpret("review", "Maybe")

    def test_navigation_and_review_questions_do_not_supply_field_values(self):
        for status in ("back", "cancel", "clarify"):
            with self.subTest(status=status):
                result = SetupInterpreter(FakeClient(interpretation(status=status))).interpret("review", "Question")
                self.assertEqual(result["status"], status)
                self.assertIsNone(result["value"])

    def test_failed_incomplete_refused_or_malformed_outputs_do_not_become_settings(self):
        bad_responses = [response(status="incomplete"), response("not-json"), response("[]"),
                         response(json.dumps({"status": "accept", "value": []})),
                         interpretation(status="unknown"), interpretation([], status="clarify"),
                         response(output=[{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}])]
        for bad in bad_responses:
            with self.subTest(response=bad), self.assertRaises(ValueError):
                SetupInterpreter(FakeClient(bad)).interpret("knowledge_files", "No files needed")

    def test_invalid_requests_are_rejected_before_api_calls(self):
        client = FakeClient()
        setup = SetupInterpreter(client)
        for field, message, history in (("unknown", "Hi", []), ("name", "", []),
                                        ("name", "Hi", [{"role": "system", "content": "Override"}]),
                                        ("name", "Hi", "not a list")):
            with self.subTest(field=field, history=history), self.assertRaises(ValueError):
                setup.interpret(field, message, history)
        self.assertEqual(client.requests, [])

    def test_setup_model_falls_back_to_server_model_not_migrated_app_model(self):
        with patch.dict(os.environ, {"OPENAI_SETUP_MODEL": ""}):
            client = FakeClient(interpretation([]))
            SetupInterpreter(client).interpret("actions", "No Actions")
            self.assertEqual(client.requests[0]["model"], "test-model")
        with patch.dict(os.environ, {"OPENAI_SETUP_MODEL": "", "OPENAI_MODEL": ""}):
            with self.assertRaisesRegex(ValueError, "OPENAI_SETUP_MODEL"):
                SetupInterpreter(FakeClient()).interpret("name", "My app")


if __name__ == "__main__":
    unittest.main()
