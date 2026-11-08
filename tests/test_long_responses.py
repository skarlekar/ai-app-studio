"""Length-limited Responses are usable partial answers, not successful completions."""
import copy
import tempfile
import unittest

from gptapps.extensions import FunctionTool, Registry
from gptapps.runtime import Runtime
from test_framework import FakeClient, app, response
from test_streaming import StreamClient, delta


def limited(text="First part of a long answer.", **overrides):
    return response(text, status="incomplete",
                    incomplete_details={"reason": "max_output_tokens"}, **overrides)


class LongResponseTests(unittest.TestCase):
    def test_explicit_length_limit_preserves_marked_text_in_json_and_streaming_chat(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming), tempfile.TemporaryDirectory() as temp:
                partial = limited("### A long answer\n\nThe first section.")
                client = (StreamClient([delta("provisional draft"),
                          {"type": "response.incomplete", "response": partial}])
                          if streaming else FakeClient(partial))
                runtime, config, events = Runtime(temp, client), app(), []
                result = runtime.chat(config, "Explain in detail", emit=events.append if streaming else None)
                self.assertEqual(result["message"]["content"], "### A long answer\n\nThe first section.")
                self.assertEqual(result["message"]["incomplete_reason"], "max_output_tokens")
                self.assertEqual(runtime.get_session(config["id"], result["session_id"])["messages"][-1],
                                 result["message"])
                self.assertEqual(len(client.requests), 1)  # No automatic retry or extra billing.

    def test_user_can_continue_from_the_saved_partial_answer(self):
        client = FakeClient(limited("First part."), response("Second part."))
        with tempfile.TemporaryDirectory() as temp:
            runtime, config = Runtime(temp, client), app()
            first = runtime.chat(config, "Explain in detail")
            self.assertEqual(len(client.requests), 1)
            second = runtime.chat(config, "Continue from where you stopped.", first["session_id"])
            self.assertEqual(second["session_id"], first["session_id"])
            self.assertEqual(client.requests[1]["input"], [
                {"role": "user", "content": "Explain in detail"},
                {"role": "assistant", "content": "First part."},
                {"role": "user", "content": "Continue from where you stopped."}])
            self.assertNotIn("incomplete_reason", second["message"])
            self.assertEqual(len(runtime.get_session(config["id"], first["session_id"])["messages"]), 4)

    def test_reasoning_only_length_limit_explains_the_budget_without_saving(self):
        client = FakeClient(limited(output=[{"type": "reasoning", "summary": []}]))
        with tempfile.TemporaryDirectory() as temp:
            runtime, config = Runtime(temp, client), app()
            config["runtime"]["max_output_tokens"] = 2048
            with self.assertRaisesRegex(ValueError, "max_output_tokens.*2,048.*reasoning"):
                runtime.chat(config, "A difficult question")
            self.assertEqual(runtime.list_sessions(config["id"]), [])
            self.assertEqual(len(client.requests), 1)

    def test_truncated_structured_output_is_not_saved_as_a_valid_answer(self):
        config = app()
        config["runtime"]["output_schema"] = {"type": "object", "properties": {}}
        with tempfile.TemporaryDirectory() as temp:
            runtime = Runtime(temp, FakeClient(limited('{"unfinished":')))
            with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                runtime.chat(config, "Return JSON")
            self.assertEqual(runtime.list_sessions(config["id"]), [])

    def test_incomplete_function_call_is_never_executed(self):
        config, registry, invocations = app(), Registry(), []
        registry.add(FunctionTool("lookup", "Look up a value", {}, lambda **kw: invocations.append(kw)))
        config["bindings"]["function_tools"] = ["lookup"]
        call = {"type": "function_call", "name": "lookup", "call_id": "unfinished",
                "arguments": '{"query":'}
        with tempfile.TemporaryDirectory() as temp:
            runtime = Runtime(temp, FakeClient(limited(output=[call])), registry)
            with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                runtime.chat(config, "Look something up")
            self.assertEqual(invocations, [])
            self.assertEqual(runtime.list_sessions(config["id"]), [])

    def test_other_incomplete_reasons_still_fail_without_saving_or_echoing_private_text(self):
        for reason in ("content_filter", "unknown private provider text", None):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temp:
                runtime = Runtime(temp, FakeClient(response("Unsafe to assume complete", status="incomplete",
                                  incomplete_details={"reason": reason})))
                with self.assertRaises(ValueError) as failure:
                    runtime.chat(app(), "Explain")
                self.assertNotIn("private provider text", str(failure.exception))
                if reason == "content_filter":
                    self.assertIn("content_filter", str(failure.exception))
                self.assertEqual(runtime.list_sessions(app()["id"]), [])

    def test_larger_explicit_budget_reaches_the_provider(self):
        config, client = app(), FakeClient(response("A full response"))
        config["runtime"]["max_output_tokens"] = 32768
        with tempfile.TemporaryDirectory() as temp:
            result = Runtime(temp, client).chat(config, "Explain in detail")
        self.assertEqual(result["message"]["content"], "A full response")
        self.assertEqual(client.requests[0]["max_output_tokens"], 32768)

    def test_new_app_budget_allows_a_response_that_outgrew_the_old_default(self):
        class BudgetClient(FakeClient):
            def create(self, payload):
                self.requests.append(copy.deepcopy(payload))
                return response("Full long answer") if payload["max_output_tokens"] >= 8192 else limited("Cut short")

        client = BudgetClient()
        with tempfile.TemporaryDirectory() as temp:
            result = Runtime(temp, client).chat(app(), "Give a long explanation")
        self.assertEqual(result["message"]["content"], "Full long answer")


if __name__ == "__main__":
    unittest.main()
