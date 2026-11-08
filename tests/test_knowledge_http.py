import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile

from gptapps.spec import import_export
from test_launchers import ROOT, request, stop, unused_port, wait_ready


class KnowledgeHTTPTests(unittest.TestCase):
    standalone = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.apps = self.folder / "apps"
        self.apps.mkdir()
        self.config = import_export(json.loads((ROOT / "examples/minimal-export.json").read_text()))[0]
        (self.apps / (self.config["id"] + ".json")).write_text(json.dumps(self.config))
        self.base = f"http://127.0.0.1:{unused_port()}"
        logfile = self.folder / "server.log"
        self.log = logfile.open("w")
        self.process = subprocess.Popen([sys.executable, str(ROOT / "tests/serve_fixture.py"), str(self.apps),
            str(self.folder / "data"), self.base.rsplit(":", 1)[1], *( ["--standalone"] if self.standalone else [])],
            stdout=self.log, stderr=self.log)
        try:
            wait_ready(self.process, self.base, logfile, builder=not self.standalone)
        except Exception:
            self.tearDown()
            raise

    def tearDown(self):
        stop(self.process)
        self.log.close()
        self.temp.cleanup()

    def upload(self, filename="guide.txt"):
        with request(self.base, "/api/knowledge", {"files": [{"name": filename, "size": 5}, {"name": "notes.md", "size": 5}]}) as result:
            job = json.load(result)
        for index, data in enumerate((b"Guide", b"Notes")):
            req = urllib.request.Request(self.base + f"/api/knowledge/file?id={job['id']}&index={index}",
                data=data, headers={"Content-Type": "application/octet-stream"})
            urllib.request.urlopen(req).close()
        with request(self.base, "/api/knowledge/index", {"upload_id": job["id"]}) as result:
            self.assertEqual(json.load(result)["status"], "indexing")
        with request(self.base, "/api/knowledge/status?id=" + job["id"]) as result:
            return json.load(result)

    def test_ready_upload_creates_bound_app_and_zip_without_document_bytes(self):
        job = self.upload()
        self.assertEqual(job["status"], "ready")
        draft = {"name": "Knowledge assistant", "instructions": "Use my knowledge exactly.", "knowledge_upload_id": job["id"]}
        with request(self.base, "/api/apps", draft) as result:
            created = json.load(result)
        self.assertTrue(created["report"]["runtime_ready"])
        with request(self.base, "/api/build?app=" + created["id"]) as result:
            with zipfile.ZipFile(io.BytesIO(result.read())) as archive:
                config = json.loads(archive.read("app.json"))
                self.assertEqual(config["instructions"], draft["instructions"])
                self.assertEqual(config["bindings"]["vector_store_ids"], [job["vector_store_id"]])
                self.assertEqual(config["requirements"]["knowledge_files"], ["guide.txt", "notes.md"])
                self.assertNotIn("knowledge", config)
                self.assertFalse(any(file["file_id"] in json.dumps(config) for file in job["files"]))
                self.assertNotIn("guide.txt", archive.namelist())
                self.assertFalse(any("knowledge-uploads/" in path for path in archive.namelist()))

    def test_existing_app_binding_is_atomic_and_preserves_other_configuration(self):
        job = self.upload()
        with request(self.base, "/api/knowledge/bind", {"app_id": self.config["id"], "upload_id": job["id"]}) as result:
            self.assertTrue(json.load(result)["report"]["runtime_ready"])
        saved = json.loads((self.apps / (self.config["id"] + ".json")).read_text())
        self.assertEqual(saved["instructions"], self.config["instructions"])
        self.assertEqual(saved["runtime"], self.config["runtime"])
        self.assertEqual(saved["bindings"]["vector_store_ids"], [job["vector_store_id"]])
        changed = {**saved, "instructions": "A concurrent edit"}
        (self.apps / (self.config["id"] + ".json")).write_text(json.dumps(changed))
        with self.assertRaises(urllib.error.HTTPError) as failure:
            request(self.base, "/api/knowledge/bind", {"app_id": self.config["id"], "upload_id": job["id"]})
        self.assertEqual(failure.exception.code, 400)
        failure.exception.close()
        self.assertEqual(json.loads((self.apps / (self.config["id"] + ".json")).read_text())["instructions"], "A concurrent edit")

    def test_pending_failed_and_unknown_uploads_cannot_be_bound(self):
        with request(self.base, "/api/knowledge", {"files": [{"name": "guide.txt", "size": 5}]}) as result:
            pending = json.load(result)
        failed = self.upload("broken.txt")
        self.assertEqual(failed["status"], "failed")
        for upload_id in (pending["id"], failed["id"], "0" * 32):
            with self.subTest(upload_id=upload_id), self.assertRaises(urllib.error.HTTPError) as failure:
                request(self.base, "/api/knowledge/bind", {"app_id": self.config["id"], "upload_id": upload_id})
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()
        self.assertEqual(json.loads((self.apps / (self.config["id"] + ".json")).read_text()), self.config)

    def test_cross_origin_upload_is_rejected(self):
        req = urllib.request.Request(self.base + "/api/knowledge", data=b"{}",
            headers={"Content-Type": "application/json", "Origin": "https://example.com"})
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(req)
        self.assertEqual(failure.exception.code, 403)
        failure.exception.close()

    def test_oversized_binary_request_is_rejected_before_reading_or_forwarding_it(self):
        req = urllib.request.Request(self.base + "/api/knowledge/file?id=unknown&index=0", data=b"x",
            headers={"Content-Type": "application/octet-stream", "Content-Length": str(25 * 1024**2 + 1)})
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(failure.exception.code, 403 if self.standalone else 400)
        failure.exception.close()


class StandaloneKnowledgeHTTPTests(KnowledgeHTTPTests):
    standalone = True

    def test_uploads_and_bindings_are_disabled(self):
        for path in ("/api/knowledge", "/api/knowledge/file", "/api/knowledge/index", "/api/knowledge/bind"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as failure:
                request(self.base, path, {"files": []})
            self.assertEqual(failure.exception.code, 403)
            failure.exception.close()
        self.assertFalse((self.folder / "data/knowledge-uploads").exists())

    # The mutation tests above exercise builder behavior, not this end-user surface.
    test_ready_upload_creates_bound_app_and_zip_without_document_bytes = None
    test_existing_app_binding_is_atomic_and_preserves_other_configuration = None
    test_pending_failed_and_unknown_uploads_cannot_be_bound = None
