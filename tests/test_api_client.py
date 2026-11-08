import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from gptapps.runtime import OpenAIClient


def provider_error(body, status=429, headers=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return urllib.error.HTTPError("https://api.openai.com/v1/responses", status, "Provider error",
                                  headers or {}, io.BytesIO(raw))


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-not-a-real-key"})
class APIClientTests(unittest.TestCase):
    def failure_message(self, body, status=429, headers=None):
        error = provider_error(body, status, headers)
        with patch("gptapps.runtime.urllib.request.urlopen", side_effect=error) as send:
            with self.assertRaises(ValueError) as failure:
                OpenAIClient().create({"model": "test-model", "input": "private user text"})
        self.assertEqual(send.call_count, 1, "Billing/quota errors and user inputs must not be replayed automatically")
        message = str(failure.exception)
        self.assertNotIn("test-only-not-a-real-key", message)
        self.assertNotIn("private user text", message)
        return message

    def test_quota_error_explains_billing_without_echoing_provider_message(self):
        message = self.failure_message({"error": {"code": "insufficient_quota", "type": "insufficient_quota",
            "message": "private user text, test-only-not-a-real-key"}})
        self.assertIn("insufficient_quota", message)
        self.assertIn("billing", message)
        self.assertIn("ChatGPT subscriptions and API billing are separate", message)
        self.assertNotIn("rate limit reached", message)

    def test_specific_credit_and_limit_codes_take_precedence_over_quota_type(self):
        cases = {
            "credit_balance_exhausted": "credit balance is exhausted",
            "organization_spend_limit_exceeded": "organization spending limit reached",
            "project_spend_limit_exceeded": "project spending limit reached",
            "organization_usage_limit_exceeded": "organization usage limit reached",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                message = self.failure_message({"error": {"code": code, "type": "insufficient_quota"}})
                self.assertIn(expected, message)
                self.assertIn(code, message)
                self.assertNotIn("(insufficient_quota)", message)

    def test_legacy_quota_type_is_recognized_when_code_is_absent(self):
        message = self.failure_message({"error": {"code": None, "type": "insufficient_quota"}})
        self.assertIn("insufficient_quota", message)

    def test_rate_limit_explains_pacing_and_retry_after_without_suggesting_credits(self):
        for code in ("rate_limit_exceeded", "rate_limit_error", "slow_down"):
            with self.subTest(code=code):
                message = self.failure_message({"error": {"code": code}}, headers={"Retry-After": "30"})
                self.assertIn(code, message)
                self.assertIn("Wait at least 30 seconds", message)
                self.assertNotIn("billing", message)
                self.assertNotIn("add API credits", message)
        message = self.failure_message({"error": {"type": "rate_limit_error", "code": None}})
        self.assertIn("rate_limit_error", message)

    def test_arbitrary_error_shapes_and_codes_remain_ambiguous_and_private(self):
        for body in (b"not-json", [], None, {"error": "private user text"},
                     {"error": {"code": "private user text"}},
                     {"error": {"code": [], "type": {"value": "private user text"}}},
                     {"error": {"message": "private user text" * 10000}}):
            with self.subTest(body_type=type(body).__name__):
                message = self.failure_message(body)
                self.assertIn("HTTP 429", message)
                self.assertIn("status alone does not identify the cause", message)

    def test_untrusted_retry_after_headers_are_not_echoed(self):
        for delay in ("private user text", "NaN", "-1", "1.5", "9" * 1000):
            with self.subTest(delay_length=len(delay)):
                message = self.failure_message({"error": {"code": "rate_limit_exceeded"}},
                                               headers={"Retry-After": delay})
                self.assertNotIn("Wait at least", message)

    def test_quota_error_does_not_suggest_retrying_even_with_retry_after_header(self):
        message = self.failure_message({"error": {"code": "insufficient_quota"}}, headers={"Retry-After": "30"})
        self.assertNotIn("Wait at least", message)

    def test_non_429_errors_still_summarize_provider_payloads(self):
        message = self.failure_message({"error": {"message": "private user text"}}, status=400)
        self.assertIn("HTTP 400", message)

    def test_transport_errors_do_not_become_quota_errors(self):
        with patch("gptapps.runtime.urllib.request.urlopen", side_effect=urllib.error.URLError("private user text")):
            with self.assertRaisesRegex(ValueError, "connection failed or timed out"):
                OpenAIClient().create({"model": "test-model"})

    def test_successful_response_and_request_settings_are_preserved(self):
        with patch("gptapps.runtime.urllib.request.urlopen", return_value=io.BytesIO(b'{"status":"completed"}')) as send:
            self.assertEqual(OpenAIClient().create({"model": "test-model", "store": False}), {"status": "completed"})
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(json.loads(request.data), {"model": "test-model", "store": False})
        self.assertEqual(send.call_args.kwargs["timeout"], 90)


if __name__ == "__main__":
    unittest.main()
