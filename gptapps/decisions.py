"""Small, bounded standard-library client for OpenAI Decisions."""
import http.client
import json
import math
import os
import urllib.error
import urllib.request


MAX_REPLY_BYTES = 65536


class DecisionsUnavailable(Exception):
    """A transient transport/server failure for which routing may use fallback."""


class DecisionsInvalid(ValueError):
    """An unusable classifier response, safe to handle as an invalid decision."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # In particular, never forward a bearer token to a different endpoint.
        return None


class DecisionsClient:
    def create(self, payload, *, timeout=2):
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not .5 <= timeout <= 10):
            raise ValueError('Routing timeout must be between 0.5 and 10 seconds')
        key = os.environ.get('OPENAI_API_KEY')
        if not key:
            raise ValueError('Set OPENAI_API_KEY to use OpenAI model routing')
        request = urllib.request.Request(
            'https://api.openai.com/v1/decisions',
            data=json.dumps(payload, allow_nan=False).encode('utf-8'),
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_REPLY_BYTES + 1)
            if len(raw) > MAX_REPLY_BYTES:
                raise DecisionsInvalid('OpenAI returned a decision exceeding the supported size')
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                raise DecisionsInvalid('OpenAI returned an invalid decision') from None
            if not isinstance(result, dict):
                raise DecisionsInvalid('OpenAI returned an invalid decision')
            answers = result.get('answers')
            if isinstance(answers, list) and any(isinstance(a, dict) and a.get('type') == 'refusal' for a in answers):
                raise ValueError('OpenAI Decisions refused classification; no answer request was started')
            return result
        except urllib.error.HTTPError as error:
            if 500 <= error.code <= 599:
                error.close()
                raise DecisionsUnavailable('OpenAI routing service is temporarily unavailable') from None
            # Lazy import avoids a runtime -> routing -> decisions -> runtime cycle.
            from .runtime import api_error_message
            raise ValueError(api_error_message(error)) from None
        except (OSError, urllib.error.URLError, http.client.HTTPException):
            raise DecisionsUnavailable('OpenAI routing connection failed or timed out') from None
