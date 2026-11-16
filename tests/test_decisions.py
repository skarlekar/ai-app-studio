import io
import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from gptapps.decisions import DecisionsClient, DecisionsUnavailable


class StubOpener:
    def __init__(self, response=None, error=None):
        self.response = response or io.BytesIO(b'{"answers": [], "usage": {}}')
        self.error = error
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


@patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-not-a-real-key',
                         'OPENAI_BASE_URL': 'https://evil.invalid'})
class DecisionsClientTests(unittest.TestCase):
    def test_fixed_endpoint_and_one_bounded_timeout_request(self):
        opener = StubOpener()
        with patch('gptapps.decisions.urllib.request.build_opener', return_value=opener):
            result = DecisionsClient().create({'model': 'gpt-6-luna', 'input': 'private'}, timeout=1.25)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/decisions')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(timeout, 1.25)
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-not-a-real-key')
        self.assertEqual(json.loads(request.data)['input'], 'private')
        self.assertEqual(result, {'answers': [], 'usage': {}})
        self.assertEqual(len(opener.calls), 1)

    def test_redirect_handler_never_forwards_credentials(self):
        real = urllib.request.build_opener
        recorded = []
        def record(*handlers):
            recorded.extend(handlers)
            return StubOpener()
        with patch('gptapps.decisions.urllib.request.build_opener', side_effect=record):
            DecisionsClient().create({'model': 'gpt-6-luna'}, timeout=2)
        handlers = [h for h in recorded if isinstance(h, urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(handlers), 1)
        request = urllib.request.Request('https://api.openai.com/v1/decisions', headers={'Authorization': 'secret'})
        self.assertIsNone(handlers[0].redirect_request(request, None, 302, 'Found', {}, 'https://evil.invalid'))

    def test_transport_timeout_and_server_errors_are_unavailable(self):
        errors = [TimeoutError('private'), ConnectionError('private'),
                  urllib.error.URLError('private'),
                  urllib.error.HTTPError('url', 503, 'private', {}, io.BytesIO(b'private'))]
        for error in errors:
            opener = StubOpener(error=error)
            with self.subTest(error=type(error).__name__), patch('gptapps.decisions.urllib.request.build_opener', return_value=opener):
                with self.assertRaises(DecisionsUnavailable) as failure:
                    DecisionsClient().create({}, timeout=2)
                self.assertNotIn('private', str(failure.exception))
                self.assertEqual(len(opener.calls), 1)

    def test_auth_quota_and_redirect_are_fatal_and_private(self):
        for status, body, expected in [(401, {'error': {'message': 'private'}}, 'HTTP 401'),
                                       (403, {}, 'HTTP 403'), (302, {}, 'HTTP 302'),
                                       (429, {'error': {'code': 'insufficient_quota', 'message': 'private'}}, 'insufficient_quota')]:
            error = urllib.error.HTTPError('url', status, 'private', {}, io.BytesIO(json.dumps(body).encode()))
            with self.subTest(status=status), patch('gptapps.decisions.urllib.request.build_opener', return_value=StubOpener(error=error)):
                with self.assertRaisesRegex(ValueError, expected) as failure:
                    DecisionsClient().create({}, timeout=2)
                self.assertNotIsInstance(failure.exception, DecisionsUnavailable)
                self.assertNotIn('private', str(failure.exception))

    def test_oversized_invalid_and_nonobject_responses_are_rejected(self):
        for raw in [b'x'*65537, b'invalid private', b'[]', b'null']:
            with self.subTest(size=len(raw)), patch('gptapps.decisions.urllib.request.build_opener', return_value=StubOpener(io.BytesIO(raw))):
                with self.assertRaisesRegex(ValueError, 'invalid|size'):
                    DecisionsClient().create({}, timeout=2)

    def test_refusal_is_fatal(self):
        raw = b'{"answers": [{"type": "refusal", "name": "effort", "refusal": "private"}]}'
        with patch('gptapps.decisions.urllib.request.build_opener', return_value=StubOpener(io.BytesIO(raw))):
            with self.assertRaisesRegex(ValueError, 'refused') as failure:
                DecisionsClient().create({}, timeout=2)
            self.assertNotIn('private', str(failure.exception))

    def test_missing_key_and_invalid_timeout_fail_without_transport(self):
        with patch.dict(os.environ, {}, clear=True), patch('gptapps.decisions.urllib.request.build_opener') as build:
            with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                DecisionsClient().create({}, timeout=2)
            build.assert_not_called()
        for timeout in [False, 0, .49, 10.1, float('nan')]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                DecisionsClient().create({}, timeout=timeout)


if __name__ == '__main__':
    unittest.main()
