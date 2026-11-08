import copy
from email import policy
from email.parser import BytesParser
from email.message import Message
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.request
import urllib.response
from unittest.mock import patch

from gptapps.knowledge import KnowledgeClient, KnowledgeManager
from gptapps.runtime import Runtime
from gptapps.spec import analyze
from test_api_client import provider_error
from test_framework import app


class FakeKnowledgeClient:
    def __init__(self):
        self.uploads = []
        self.stores = 0
        self.batches = 0
        self.fail_upload = False
        self.fail_index = False

    def create_store(self):
        self.stores += 1
        return {"id": f"vs_{self.stores}"}

    def upload_file(self, name, data):
        if self.fail_upload:
            raise ValueError("OpenAI returned HTTP 401; check model access, tools, billing and limits")
        self.uploads.append((name, data))
        return {"id": f"file-{len(self.uploads)}"}

    def create_batch(self, store, files):
        self.batches += 1
        self.total = len(files)
        self.store = store
        return self.batch("in_progress")

    def batch(self, status):
        failed = int(self.fail_index)
        return {"id": "vsfb_batch", "vector_store_id": self.store, "status": status,
                "file_counts": {"total": self.total, "completed": self.total - failed if status == "completed" else 0,
                                "failed": failed, "cancelled": 0, "in_progress": self.total if status == "in_progress" else 0}}

    def get_batch(self, store, batch):
        return self.batch("completed")


def start_pair(manager):
    job = manager.start([{"name": "guide.txt", "size": 5}, {"name": "notes.md", "size": 5}])
    manager.upload(job["id"], 0, b"Guide")
    manager.upload(job["id"], 1, b"Notes")
    return job["id"]


class KnowledgeManagerTests(unittest.TestCase):
    def test_ready_collection_can_attach_to_a_valid_manifest_without_requirements(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = KnowledgeManager(temp, FakeKnowledgeClient())
            upload_id = start_pair(manager)
            manager.index(upload_id)
            config = app()
            del config["requirements"]
            self.assertTrue(analyze(config)["runtime_ready"])
            attached = manager.apply(upload_id, config)
            self.assertEqual(attached["requirements"]["knowledge_files"], ["guide.txt", "notes.md"])
            self.assertNotIn("knowledge", attached)  # Per-file provider metadata stays in local upload records.

    def test_multiple_files_survive_restart_and_bind_only_after_full_indexing(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeKnowledgeClient()
            manager = KnowledgeManager(temp, client)
            upload_id = start_pair(manager)
            with self.assertRaisesRegex(ValueError, "ready"):
                manager.apply(upload_id, app())
            restarted = KnowledgeManager(temp, client)
            self.assertEqual(len(restarted.get(upload_id)["files"]), 2)
            self.assertEqual(restarted.index(upload_id)["status"], "indexing")
            self.assertEqual(restarted.get(upload_id, refresh=True)["status"], "ready")
            original = app()
            original["requirements"]["knowledge_files"] = ["old.txt"]
            result = restarted.apply(upload_id, original)
            self.assertEqual(result["bindings"]["vector_store_ids"], ["vs_1"])
            self.assertEqual(result["requirements"]["knowledge_files"], ["guide.txt", "notes.md"])
            self.assertEqual(result["instructions"], original["instructions"])
            self.assertEqual(result["runtime"], original["runtime"])
            self.assertTrue(analyze(result)["runtime_ready"])
            self.assertEqual(original["bindings"]["vector_store_ids"], [])
            restarted.claim(upload_id, original["id"])
            self.assertIn(original["id"], restarted.get(upload_id)["app_ids"])
            self.assertEqual(Runtime(Path(temp) / "chat", client).configuration(result)[1],
                             [{"type": "file_search", "vector_store_ids": ["vs_1"]}])

    def test_repeated_file_and_index_requests_do_not_duplicate_provider_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeKnowledgeClient()
            manager = KnowledgeManager(temp, client)
            upload_id = start_pair(manager)
            manager.upload(upload_id, 0, b"Guide")
            self.assertEqual(len(client.uploads), 2)
            with self.assertRaisesRegex(ValueError, "match"):
                manager.upload(upload_id, 0, b"Other")
            manager.index(upload_id)
            manager.index(upload_id)
            self.assertEqual(client.batches, 1)

    def test_partial_indexing_failure_cannot_unblock_an_app(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeKnowledgeClient()
            client.fail_index = True
            manager = KnowledgeManager(temp, client)
            upload_id = start_pair(manager)
            manager.index(upload_id)
            self.assertEqual(manager.get(upload_id, refresh=True)["status"], "failed")
            with self.assertRaisesRegex(ValueError, "ready"):
                manager.apply(upload_id, app())

    def test_invalid_files_are_rejected_before_any_provider_request(self):
        cases = [[], [{"name": "../guide.txt", "size": 1}], [{"name": "guide.csv", "size": 1}],
                 [{"name": "guide.txt", "size": 0}], [{"name": "guide.txt", "size": 26 * 1024**2}],
                 [{"name": "guide.txt", "size": True}], [{"name": "bad\r\n.txt", "size": 1}],
                 [{"name": f"guide-{i}.txt", "size": 25 * 1024**2} for i in range(5)],
                 [{"name": "guide.txt", "size": 1}] * 101]
        with tempfile.TemporaryDirectory() as temp:
            client = FakeKnowledgeClient()
            manager = KnowledgeManager(temp, client)
            for files in cases:
                with self.subTest(files=files[:1]), self.assertRaises(ValueError):
                    manager.start(files)
            self.assertEqual(client.stores, 0)
            self.assertEqual(manager.list(), [])

    def test_wrong_size_slots_and_upload_ids_fail_without_uploading(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeKnowledgeClient()
            manager = KnowledgeManager(temp, client)
            job = manager.start([{"name": "guide.txt", "size": 5}])
            for upload_id, slot, data in (("../other", 0, b"Guide"), (job["id"], -1, b"Guide"),
                                          (job["id"], 1, b"Guide"), (job["id"], 0, b"too long")):
                with self.subTest(slot=slot), self.assertRaises(ValueError):
                    manager.upload(upload_id, slot, data)
            self.assertEqual(client.uploads, [])
            with self.assertRaisesRegex(ValueError, "Upload all"):
                manager.index(job["id"])

    def test_failed_upload_is_recorded_without_storing_document_bytes_or_retrying(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeKnowledgeClient()
            client.fail_upload = True
            manager = KnowledgeManager(temp, client)
            job = manager.start([{"name": "guide.txt", "size": 24}])
            with self.assertRaises(ValueError):
                manager.upload(job["id"], 0, b"Private document content")
            self.assertEqual(manager.get(job["id"])["status"], "failed")
            self.assertNotIn(b"Private document content", b"".join(p.read_bytes() for p in Path(temp).rglob("*") if p.is_file()))
            with self.assertRaisesRegex(ValueError, "ready"):
                manager.apply(job["id"], app())


class KnowledgeClientTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-not-a-real-key"})
    def test_redirects_are_rejected_before_a_second_authenticated_request(self):
        seen = []
        def response(handler, request):
            seen.append(request)
            headers = Message()
            if len(seen) == 1:
                headers["Location"] = "https://untrusted.example/collect"
                result = urllib.response.addinfourl(io.BytesIO(b""), headers, request.full_url, 302)
                result.msg = "Found"
            else:
                result = urllib.response.addinfourl(io.BytesIO(b'{"id":"vs_redirected"}'), headers, request.full_url, 200)
                result.msg = "OK"
            return result
        with patch.object(urllib.request.HTTPSHandler, "https_open", response):
            with self.assertRaisesRegex(ValueError, "redirect"):
                KnowledgeClient().create_store()
        self.assertEqual(len(seen), 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-not-a-real-key"})
    def test_files_multipart_and_vector_batch_use_documented_endpoints(self):
        records = []
        def send(request, timeout):
            records.append(request)
            return io.BytesIO(json.dumps({"id": "file-test"}).encode())
        with patch("gptapps.knowledge.urllib.request.OpenerDirector.open", side_effect=send):
            client = KnowledgeClient()
            client.upload_file("résumé.txt", b"Document bytes")
            client.create_store()
            client.create_batch("vs_test", ["file-test", "file-second"])
            client.get_batch("vs_test", "vsfb_test")
        self.assertEqual([r.full_url for r in records], ["https://api.openai.com/v1/files",
            "https://api.openai.com/v1/vector_stores", "https://api.openai.com/v1/vector_stores/vs_test/file_batches",
            "https://api.openai.com/v1/vector_stores/vs_test/file_batches/vsfb_test"])
        self.assertEqual(records[0].get_header("Authorization"), "Bearer test-not-a-real-key")
        parsed = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + records[0].get_header("Content-type") + "\r\n\r\n").encode() + records[0].data)
        parts = {p.get_param("name", header="content-disposition"): p for p in parsed.iter_parts()}
        self.assertEqual(parts["purpose"].get_payload(decode=True), b"assistants")
        self.assertEqual(parts["file"].get_filename(), "résumé.txt")
        self.assertEqual(parts["file"].get_payload(decode=True), b"Document bytes")
        self.assertEqual(json.loads(records[2].data), {"file_ids": ["file-test", "file-second"]})
        self.assertEqual(records[3].get_method(), "GET")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-not-a-real-key"})
    def test_provider_failures_remain_sanitized_and_are_not_retried(self):
        error = provider_error({"error": {"code": "insufficient_quota", "message": "Private document content"}})
        with patch("gptapps.knowledge.urllib.request.OpenerDirector.open", side_effect=error) as send:
            with self.assertRaisesRegex(ValueError, "insufficient_quota") as failure:
                KnowledgeClient().create_store()
        self.assertNotIn("Private document content", str(failure.exception))
        self.assertEqual(send.call_count, 1)
