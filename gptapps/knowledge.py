"""Owner-selected knowledge uploads. Only metadata and provider IDs persist locally."""
import copy
import hashlib
import http.client
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

from .runtime import api_error_message
from .spec import validate

MAX_FILES = 100
MAX_FILE_BYTES = 25 * 1024**2
MAX_TOTAL_BYTES = 100 * 1024**2
EXTENSIONS = (".c", ".cpp", ".cs", ".css", ".doc", ".docx", ".go", ".html", ".java", ".js",
              ".json", ".md", ".pdf", ".php", ".pptx", ".py", ".rb", ".sh", ".tex", ".ts", ".txt")


def provider_id(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_-]{1,200}", value):
        raise ValueError("OpenAI returned an invalid knowledge resource identifier")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        response.close()
        raise ValueError("OpenAI knowledge redirects are disabled; credentials and files were not forwarded")


class KnowledgeClient:
    def __init__(self):
        self.opener = urllib.request.build_opener(_NoRedirect())

    def request(self, path, payload=None, *, raw=None, content_type="application/json", method="POST"):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("Set OPENAI_API_KEY in the server environment")
        data = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {key}", "Content-Type": content_type}
        if path.startswith("/vector_stores"):
            headers["OpenAI-Beta"] = "assistants=v2"
        request = urllib.request.Request("https://api.openai.com/v1" + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=90) as response:
                body = response.read(1024**2 + 1)
            if len(body) > 1024**2:
                raise ValueError("OpenAI knowledge response exceeded the supported size")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError("OpenAI returned an invalid knowledge response")
            return result
        except urllib.error.HTTPError as exc:
            raise ValueError(api_error_message(exc)) from None
        except (OSError, http.client.HTTPException):
            raise ValueError("OpenAI knowledge connection failed or timed out. Check recent uploads before starting another collection.") from None
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("OpenAI returned an invalid knowledge response") from None

    def create_store(self):
        return self.request("/vector_stores", {"name": "GPT App knowledge"})

    def upload_file(self, name, data):
        boundary = "gptapps-" + uuid.uuid4().hex
        filename = name.replace("\\", "\\\\").replace('"', '\\"')
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        header = (f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nassistants\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                  f'Content-Type: {kind}\r\n\r\n').encode()
        body = header + data + f"\r\n--{boundary}--\r\n".encode()
        return self.request("/files", raw=body, content_type=f"multipart/form-data; boundary={boundary}")

    def create_batch(self, store_id, file_ids):
        store_id = provider_id(store_id, "vs_")
        for file_id in file_ids:
            provider_id(file_id, "file-")
        return self.request(f"/vector_stores/{store_id}/file_batches", {"file_ids": file_ids})

    def get_batch(self, store_id, batch_id):
        store_id, batch_id = provider_id(store_id, "vs_"), provider_id(batch_id, "vsfb_")
        return self.request(f"/vector_stores/{store_id}/file_batches/{batch_id}", method="GET")


class KnowledgeManager:
    def __init__(self, data_dir, client=None):
        self.folder = Path(data_dir) / "knowledge-uploads"
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.client = client or KnowledgeClient()
        self.lock = threading.RLock()
        self.jobs = {}
        for path in self.folder.glob("*.json"):
            if not re.fullmatch(r"[a-f0-9]{32}", path.stem):
                continue
            job = json.loads(path.read_text())
            if not isinstance(job, dict) or job.get("id") != path.stem:
                raise ValueError("Invalid saved knowledge upload metadata")
            self.jobs[job["id"]] = job
            if job["status"] == "creating" or any(f["status"] == "uploading" for f in job["files"]) or (job["status"] == "indexing" and not job.get("batch_id")):
                job["status"] = "failed"
                job["error"] = "Upload was interrupted. Check the recorded OpenAI resources before starting another collection."
                self._save(job)

    def _save(self, job):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.folder, delete=False) as file:
            temp = Path(file.name)
            try:
                json.dump(job, file, ensure_ascii=False)
                file.write("\n")
                file.close()
                temp.replace(self.folder / (job["id"] + ".json"))
            finally:
                temp.unlink(missing_ok=True)

    def _job(self, upload_id):
        if not isinstance(upload_id, str) or not re.fullmatch(r"[a-f0-9]{32}", upload_id) or upload_id not in self.jobs:
            raise ValueError("Unknown knowledge upload")
        return self.jobs[upload_id]

    def _failed(self, job, error):
        job["status"] = "failed"
        job["error"] = str(error) if isinstance(error, ValueError) else "Knowledge upload failed; check recent uploads before starting another collection."
        self._save(job)

    def start(self, files):
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
            raise ValueError(f"Choose 1–{MAX_FILES} knowledge files")
        names, total, entries = set(), 0, []
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("Invalid knowledge file metadata")
            name, size = item.get("name"), item.get("size")
            if (not isinstance(name, str) or not 1 <= len(name) <= 300 or any(ord(c) < 32 or ord(c) == 127 for c in name)
                    or "/" in name or "\\" in name or Path(name).suffix.lower() not in EXTENSIONS):
                raise ValueError("Choose supported documents with plain filenames (PDF, Word, PowerPoint, text, Markdown, JSON, or supported code files)")
            if type(size) is not int or not 0 < size <= MAX_FILE_BYTES:
                raise ValueError("Each knowledge file must be nonempty and at most 25 MiB")
            if name.casefold() in names:
                raise ValueError("Knowledge filenames must be unique within a collection")
            names.add(name.casefold())
            total += size
            entries.append({"name": name, "size": size, "status": "queued"})
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Choose at most 100 MiB of knowledge files per collection")
        with self.lock:
            job = {"id": uuid.uuid4().hex, "created_at": time.time(), "status": "creating", "files": entries,
                   "vector_store_id": None, "batch_id": None, "app_ids": [], "error": None}
            self.jobs[job["id"]] = job
            self._save(job)
            try:
                job["vector_store_id"] = provider_id(self.client.create_store().get("id"), "vs_")
                job["status"] = "uploading"
                self._save(job)
            except Exception as error:
                self._failed(job, error)
                raise
            return copy.deepcopy(job)

    def upload(self, upload_id, index, data):
        with self.lock:
            job = self._job(upload_id)
            if type(index) is not int or not 0 <= index < len(job["files"]):
                raise ValueError("Unknown knowledge file slot")
            file = job["files"][index]
            if not isinstance(data, bytes) or len(data) != file["size"] or len(data) > MAX_FILE_BYTES:
                raise ValueError("File bytes do not match the declared size")
            digest = hashlib.sha256(data).hexdigest()
            if file["status"] == "uploaded":
                if digest != file["sha256"]:
                    raise ValueError("File bytes do not match the existing upload")
                return copy.deepcopy(job)
            if job["status"] != "uploading" or file["status"] != "queued":
                raise ValueError("This collection cannot accept more files; check its status before starting another")
            file["status"] = "uploading"
            self._save(job)
            try:
                file["file_id"] = provider_id(self.client.upload_file(file["name"], data).get("id"), "file-")
                file.update(status="uploaded", sha256=digest)
                self._save(job)
            except Exception as error:
                file["status"] = "failed"
                self._failed(job, error)
                raise
            return copy.deepcopy(job)

    def _batch(self, job, batch):
        batch_id = provider_id(batch.get("id"), "vsfb_")
        if batch.get("vector_store_id") != job["vector_store_id"]:
            raise ValueError("OpenAI returned a mismatched knowledge collection")
        if job["batch_id"] and batch_id != job["batch_id"]:
            raise ValueError("OpenAI returned a mismatched knowledge batch")
        counts = batch.get("file_counts")
        if (not isinstance(counts, dict) or any(type(counts.get(k)) is not int or counts[k] < 0
                                               for k in ("total", "completed", "failed", "cancelled", "in_progress"))
                or counts["total"] != len(job["files"])):
            raise ValueError("OpenAI returned invalid knowledge indexing counts")
        status = batch.get("status")
        if status not in ("in_progress", "completed", "failed", "cancelled"):
            raise ValueError("OpenAI returned an invalid knowledge indexing status")
        job["batch_id"], job["file_counts"] = batch_id, counts
        if status in ("failed", "cancelled") or counts["failed"] or counts["cancelled"]:
            job["status"] = "failed"
            job["error"] = "Some knowledge files failed to index. Check document formats and your OpenAI project; this collection has not been attached."
        elif status == "completed":
            if counts["completed"] != len(job["files"]) or counts["in_progress"]:
                raise ValueError("OpenAI reported an incomplete knowledge batch as completed")
            job["status"] = "ready"
        else:
            job["status"] = "indexing"
        self._save(job)

    def index(self, upload_id):
        with self.lock:
            job = self._job(upload_id)
            if job["batch_id"]:
                return copy.deepcopy(job)
            if job["status"] != "uploading" or any(f["status"] != "uploaded" for f in job["files"]):
                raise ValueError("Upload all files successfully before indexing")
            job["status"] = "indexing"
            self._save(job)
            try:
                batch = self.client.create_batch(job["vector_store_id"], [f["file_id"] for f in job["files"]])
                self._batch(job, batch)
            except Exception as error:
                self._failed(job, error)
                raise
            return copy.deepcopy(job)

    def get(self, upload_id, refresh=False):
        with self.lock:
            job = self._job(upload_id)
            if refresh and job["batch_id"] and job["status"] in ("indexing", "ready"):
                self._batch(job, self.client.get_batch(job["vector_store_id"], job["batch_id"]))
            return copy.deepcopy(job)

    def list(self):
        with self.lock:
            return copy.deepcopy(sorted(self.jobs.values(), key=lambda job: job["created_at"], reverse=True)[:100])

    def apply(self, upload_id, app):
        job = self.get(upload_id, refresh=True)
        if job["status"] != "ready":
            raise ValueError("Knowledge files are not ready; upload and index every file before attaching them")
        result = copy.deepcopy(app)
        result["bindings"]["vector_store_ids"] = [job["vector_store_id"]]
        result.setdefault("requirements", {})["knowledge_files"] = [file["name"] for file in job["files"]]
        result.pop("knowledge", None)  # Keep per-file provider metadata in the local upload record.
        return validate(result)

    def claim(self, upload_id, app_id):
        with self.lock:
            job = self._job(upload_id)
            if app_id not in job["app_ids"]:
                job["app_ids"].append(app_id)
                self._save(job)
