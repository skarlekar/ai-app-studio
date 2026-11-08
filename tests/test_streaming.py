import io
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from gptapps.extensions import Registry, scoring_example
from gptapps.runtime import OpenAIClient, Runtime, sse_events
from gptapps.spec import import_export
from test_api_client import provider_error
from test_framework import app, response
from test_launchers import ROOT, request, stop, unused_port, wait_ready


def encoded(*events):
    return b"".join(("data: " + json.dumps(event, ensure_ascii=False) + "\r\n\r\n").encode() for event in events)


def delta(text, **extra):
    return {"type": "response.output_text.delta", "delta": text, "output_index": 0, "content_index": 0, **extra}


class StreamClient:
    def __init__(self, *rounds):
        self.rounds = iter(rounds)
        self.requests = []
        self.closed = 0

    def stream(self, payload):
        self.requests.append(payload)
        try:
            yield from next(self.rounds)
        finally:
            self.closed += 1


class ProviderStreamTests(unittest.TestCase):
    def test_sse_comments_multiline_utf8_and_final_frame_at_eof(self):
        raw = b': heartbeat\r\nevent: response.output_text.delta\r\ndata: {"type":"delta",\r\ndata: "delta":"' + "¡Hola!".encode() + b'"}\r\n\r\ndata: {"type":"end"}'
        self.assertEqual(list(sse_events(io.BytesIO(raw))), [{"type": "delta", "delta": "¡Hola!"}, {"type": "end"}])

    def test_invalid_provider_frames_do_not_echo_their_contents(self):
        for raw in (b'data: private instructions\n\n', b'data: []\n\n', b'data: \xff\n\n'):
            with self.subTest(raw_length=len(raw)), self.assertRaisesRegex(ValueError, "invalid streaming event"):
                list(sse_events(io.BytesIO(raw)))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-not-a-real-key"})
    def test_actual_provider_request_enables_streaming_and_closes_connection(self):
        body = io.BytesIO(encoded(delta("Hello"), {"type": "response.completed", "response": response()}))
        with patch("gptapps.runtime.urllib.request.urlopen", return_value=body) as send:
            stream = OpenAIClient().stream({"model": "test-model", "store": False})
            self.assertEqual(next(stream)["delta"], "Hello")
            stream.close()
        self.assertTrue(body.closed)
        req = send.call_args.args[0]
        self.assertTrue(json.loads(req.data)["stream"])
        self.assertFalse(json.loads(req.data)["store"])
        self.assertEqual(req.get_header("Accept"), "text/event-stream")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-not-a-real-key"})
    def test_streaming_preserves_quota_diagnostics_without_retrying(self):
        error = provider_error({"error": {"code": "insufficient_quota", "message": "private instructions"}})
        with patch("gptapps.runtime.urllib.request.urlopen", side_effect=error) as send:
            with self.assertRaisesRegex(ValueError, "insufficient_quota") as failure:
                list(OpenAIClient().stream({"model": "test-model"}))
        self.assertNotIn("private instructions", str(failure.exception))
        self.assertEqual(send.call_count, 1)


class StreamingRuntimeTests(unittest.TestCase):
    def test_text_is_emitted_before_successful_turn_is_saved(self):
        client = StreamClient([delta("¡Hola"), delta("!"), {"type": "response.completed", "response": response("¡Hola!")}])
        with tempfile.TemporaryDirectory() as temp:
            runtime, events = Runtime(temp, client), []
            def emit(event):
                self.assertEqual(runtime.list_sessions(app()["id"]), [])
                events.append(event)
            result = runtime.chat(app(), "Hello", emit=emit)
            self.assertEqual(result["message"]["content"], "¡Hola!")
            self.assertEqual("".join(e["delta"] for e in events if e["type"] == "delta"), "¡Hola!")
            self.assertEqual(len(runtime.get_session(app()["id"], result["session_id"])["messages"]), 2)
            self.assertEqual(client.closed, 1)

    def test_failed_or_truncated_stream_never_saves_partial_text(self):
        for ending in (None, "response.failed", "response.incomplete", "error"):
            events = [delta("Partial")]
            if ending:
                events.append({"type": ending, "message": "private provider text"})
            with self.subTest(ending=ending), tempfile.TemporaryDirectory() as temp:
                runtime = Runtime(temp, StreamClient(events))
                with self.assertRaises(ValueError) as failure:
                    runtime.chat(app(), "Hello", emit=lambda event: None)
                self.assertNotIn("private provider text", str(failure.exception))
                self.assertEqual(runtime.list_sessions(app()["id"]), [])

    def test_disconnected_consumer_closes_upstream_and_saves_nothing(self):
        client = StreamClient([delta("Partial"), {"type": "response.completed", "response": response()}])
        with tempfile.TemporaryDirectory() as temp:
            runtime = Runtime(temp, client)
            def emit(event):
                if event["type"] == "delta":
                    raise BrokenPipeError("Disconnected")
            with self.assertRaises(BrokenPipeError):
                runtime.chat(app(), "Hello", emit=emit)
            self.assertEqual(client.closed, 1)
            self.assertEqual(runtime.list_sessions(app()["id"]), [])

    def test_function_rounds_stream_and_reset_without_exposing_internal_events(self):
        registry = Registry()
        scoring_example(registry)
        config = app()
        config["bindings"]["function_tools"] = ["cosine_score"]
        call = {"type": "function_call", "name": "cosine_score", "call_id": "call-1",
                "arguments": json.dumps({"left": [1, 0], "right": [0, 1]})}
        client = StreamClient([
            delta("I will calculate it."), {"type": "response.reasoning_text.delta", "delta": "private reasoning"},
            {"type": "response.completed", "response": response(output=[call])}],
            [delta("50%"), {"type": "response.completed", "response": response("50%")}])
        events = []
        with tempfile.TemporaryDirectory() as temp:
            result = Runtime(temp, client, registry).chat(config, "Score", emit=events.append)
        self.assertEqual(result["message"]["content"], "50%")
        self.assertEqual(sum(e["type"] == "reset" for e in events), 2)
        self.assertNotIn("private reasoning", str(events))
        self.assertEqual(json.loads(client.requests[1]["input"][-1]["output"])["percentage"], 50)

    def test_refusals_and_citations_use_the_completed_response(self):
        completed = response(output=[{"type": "message", "content": [
            {"type": "refusal", "refusal": "Cannot help."},
            {"type": "output_text", "text": "Read more.", "annotations": [
                {"type": "url_citation", "title": "Source", "url": "https://example.com"}]}]}])
        events = []
        client = StreamClient([delta("Cannot help.", type="response.refusal.delta"),
                               {"type": "response.completed", "response": completed}])
        with tempfile.TemporaryDirectory() as temp:
            result = Runtime(temp, client).chat(app(), "Hi", emit=events.append)
        self.assertEqual(result["message"]["content"], "Cannot help.\nRead more.")
        self.assertEqual(result["message"]["citations"][0]["url"], "https://example.com")


class StreamingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        apps = self.folder / "apps"
        apps.mkdir()
        config = import_export(json.loads((ROOT / "examples/minimal-export.json").read_text()))[0]
        self.app_id = config["id"]
        (apps / (self.app_id + ".json")).write_text(json.dumps(config))
        self.port = unused_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.gate = self.folder / "release-stream"
        logfile = self.folder / "server.log"
        self.log = logfile.open("w")
        self.process = subprocess.Popen([sys.executable, str(ROOT / "tests/serve_fixture.py"),
            str(apps), str(self.folder / "data"), str(self.port)], stdout=self.log, stderr=self.log,
            env={**os.environ, "OPENAI_MODEL": "test-model", "GPTAPPS_STREAM_GATE": str(self.gate)})
        try:
            wait_ready(self.process, self.base, logfile)
        except Exception:
            self.tearDown()
            raise

    def tearDown(self):
        stop(self.process)
        self.log.close()
        self.temp.cleanup()

    def test_http_flushes_text_before_provider_completion_and_commits_only_afterwards(self):
        with request(self.base, "/api/chat", {"app_id": self.app_id, "message": "gated-stream", "stream": True}) as stream:
            self.assertIn("text/event-stream", stream.headers["Content-Type"])
            events = sse_events(stream)
            self.assertEqual(next(events)["type"], "reset")
            self.assertEqual(next(events)["delta"], "First chunk. ")
            self.assertFalse(self.gate.exists())
            with closing(sqlite3.connect(self.folder / "data/sessions.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.gate.touch()
            remaining = list(events)
        self.assertEqual(remaining[-1]["type"], "done")
        self.assertEqual(remaining[-1]["message"]["content"], "First chunk. Final chunk.")
        with request(self.base, "/api/sessions?app=" + self.app_id) as result:
            self.assertEqual(len(json.load(result)), 1)

    def test_partial_http_failure_emits_error_and_does_not_save(self):
        with request(self.base, "/api/chat", {"app_id": self.app_id, "message": "stream-fail", "stream": True}) as stream:
            events = list(sse_events(stream))
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("incomplete", events[-1]["error"])
        self.assertFalse(any(event["type"] == "done" for event in events))
        with request(self.base, "/api/sessions?app=" + self.app_id) as result:
            self.assertEqual(json.load(result), [])

    def test_length_limited_text_is_delivered_saved_and_can_be_continued(self):
        with request(self.base, "/api/chat", {"app_id": self.app_id, "message": "long-answer", "stream": True}) as stream:
            events = list(sse_events(stream))
        self.assertTrue(any(event["type"] == "delta" for event in events))
        self.assertEqual(events[-1]["type"], "done")
        saved = events[-1]
        self.assertEqual(saved["message"]["incomplete_reason"], "max_output_tokens")
        self.assertIn("saved first part", saved["message"]["content"])
        with request(self.base, "/api/sessions?app=" + self.app_id + "&id=" + saved["session_id"]) as result:
            self.assertEqual(json.load(result)["messages"][-1], saved["message"])
        with request(self.base, "/api/chat", {"app_id": self.app_id, "session_id": saved["session_id"],
                                             "message": "Continue", "stream": True}) as stream:
            continued = list(sse_events(stream))[-1]
        self.assertEqual(continued["type"], "done")
        self.assertEqual(continued["session_id"], saved["session_id"])
        self.assertNotIn("incomplete_reason", continued["message"])

    def test_plain_json_clients_still_work_and_static_assets_are_bundled(self):
        with request(self.base, "/api/chat", {"app_id": self.app_id, "message": "Hello"}) as result:
            self.assertEqual(json.load(result)["message"]["content"], "Test provider response: Hello")
        for asset, kind in (("chat.js", "text/javascript"), ("knowledge.js", "text/javascript"), ("chat.css", "text/css"),
                            ("icons/plus.svg", "image/svg+xml"),
                            ("vendor/marked.umd.js", "text/javascript"), ("vendor/purify.min.js", "text/javascript")):
            with request(self.base, "/static/" + asset) as result:
                self.assertIn(kind, result.headers["Content-Type"])
                self.assertGreater(len(result.read()), 100)
        with request(self.base, "/") as result:
            self.assertIn("script-src 'self';", result.headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
