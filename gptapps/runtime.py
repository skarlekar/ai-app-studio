import base64
import copy
from contextlib import closing
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid

from .attachments import validate_attachments, input_content, public_attachments, MAX_TOTAL_BYTES as MAX_ATTACHMENT_BYTES
from .extensions import Registry
from .spec import analyze, validate


def api_error_message(error):
    """Classify provider errors using known codes, never echo arbitrary provider text."""
    try:
        body = json.loads(error.read(65536))
    except (ValueError, OSError):
        body = None
    finally:
        error.close()
    detail = body.get("error") if isinstance(body, dict) else None
    detail = detail if isinstance(detail, dict) else {}
    if error.code == 429:
        messages = {
            "credit_balance_exhausted":
                "OpenAI API credit balance is exhausted (credit_balance_exhausted). "
                "Check or add API credits at https://platform.openai.com/settings/organization/billing. "
                "Retrying will not restore credits. ChatGPT subscriptions and API billing are separate.",
            "organization_spend_limit_exceeded":
                "OpenAI API organization spending limit reached (organization_spend_limit_exceeded). "
                "Review the organization spend limit at https://platform.openai.com/settings/organization/limits "
                "or wait for the monthly limit to reset. Retrying will not raise this limit.",
            "project_spend_limit_exceeded":
                "OpenAI API project spending limit reached (project_spend_limit_exceeded). "
                "Review the spend limit in the API key's project settings or wait for the monthly limit to reset. "
                "Retrying will not raise this limit.",
            "organization_usage_limit_exceeded":
                "OpenAI API organization usage limit reached (organization_usage_limit_exceeded). "
                "Request a higher approved usage limit at https://platform.openai.com/settings/organization/limits "
                "or contact OpenAI support. Retrying will not raise this limit.",
            "insufficient_quota":
                "OpenAI API quota is unavailable (insufficient_quota). Check API credits at "
                "https://platform.openai.com/settings/organization/billing and usage limits at "
                "https://platform.openai.com/settings/organization/limits for the API key's organization/project. "
                "Retrying will not restore quota. ChatGPT subscriptions and API billing are separate.",
            "rate_limit_exceeded":
                "OpenAI API rate limit reached (rate_limit_exceeded). "
                "Wait before trying again and reduce request frequency or concurrency. "
                "Check requests/token limits at https://platform.openai.com/settings/organization/limits.",
            "rate_limit_error":
                "OpenAI API rate limit reached (rate_limit_error). "
                "Wait before trying again and reduce request frequency or concurrency.",
            "slow_down":
                "OpenAI API requests increased too quickly (slow_down). "
                "Wait before trying again, reduce request frequency, and increase traffic gradually.",
        }
        # A specific code takes precedence over a broad type such as insufficient_quota.
        code, kind = detail.get("code"), detail.get("type")
        key = code if isinstance(code, str) and code in messages else kind
        message = messages.get(key) if isinstance(key, str) else None
        message = message or (
            "OpenAI returned HTTP 429 without a recognized error code. This can mean a temporary rate limit "
            "or exhausted API credits/quota. Check API billing and usage limits; the status alone does not identify the cause."
        )
        if key in ("rate_limit_exceeded", "rate_limit_error", "slow_down"):
            # Only display a bounded, numeric delay; arbitrary header text may contain private data.
            delay = error.headers.get("Retry-After", "") if error.headers else ""
            if isinstance(delay, str) and delay.isascii() and delay.isdigit() and len(delay) <= 6:
                message += f" Wait at least {int(delay)} seconds, as requested by OpenAI."
        return message
    return f"OpenAI returned HTTP {error.code}; check model access, tools, billing and limits"


def sse_events(response):
    """Read UTF-8 SSE data frames without buffering the entire response."""
    data = []
    size = 0
    while True:
        raw = response.readline(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("OpenAI streaming event exceeded the supported size")
        if raw:
            try:
                line = raw.decode("utf-8").rstrip("\r\n")
            except UnicodeError:
                raise ValueError("OpenAI returned an invalid streaming event") from None
        else:
            line = ""
        if not line:
            if data:
                text = "\n".join(data)
                if text == "[DONE]":
                    return
                try:
                    event = json.loads(text)
                except ValueError:
                    raise ValueError("OpenAI returned an invalid streaming event") from None
                if not isinstance(event, dict):
                    raise ValueError("OpenAI returned an invalid streaming event")
                yield event
                data, size = [], 0
            if not raw:
                return
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
            size += len(raw)
            if size > 64 * 1024 * 1024:
                raise ValueError("OpenAI streaming event exceeded the supported size")


def response_failure_message(response, token_limit):
    """Explain known terminal reasons without exposing provider messages or reasoning."""
    details = response.get("incomplete_details")
    reason = details.get("reason") if isinstance(details, dict) else None
    if response.get("status") == "incomplete" and reason == "max_output_tokens":
        return (f"OpenAI reached max_output_tokens ({token_limit:,} tokens, including reasoning). "
                "No usable complete answer was returned; no conversation turn was saved. "
                "Increase runtime.max_output_tokens in the application configuration, within your model's limit, "
                "or ask for a shorter response. Incomplete structured output and tool calls are not saved or executed.")
    if response.get("status") == "incomplete" and reason == "content_filter":
        return "OpenAI stopped the response (content_filter); no conversation turn was saved."
    return "OpenAI response was incomplete or failed; no conversation turn was saved"


class OpenAIClient:
    """Server-side API client. Keys are never included in manifests or UI payloads."""
    def request(self, payload):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("Set OPENAI_API_KEY in the server environment")
        return urllib.request.Request("https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def create(self, payload):
        request = self.request(payload)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not send provider payloads, submitted instructions, or headers to the browser.
            raise ValueError(api_error_message(exc)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("OpenAI connection failed or timed out") from None

    def stream(self, payload):
        request = self.request({**payload, "stream": True})
        request.add_header("Accept", "text/event-stream")
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                yield from sse_events(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(api_error_message(exc)) from None
        except (OSError, http.client.HTTPException):
            raise ValueError("OpenAI streaming connection failed or timed out; no conversation turn was saved") from None


class Runtime:
    def __init__(self, data_dir, client=None, registry=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.assets = self.data_dir / "assets"
        self.assets.mkdir(exist_ok=True, mode=0o700)
        self.db_path = self.data_dir / "sessions.sqlite3"
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, app_id TEXT, fingerprint TEXT, messages TEXT)")
        self.db_path.chmod(0o600)
        self.client = client or OpenAIClient()
        self.registry = registry or Registry()
        self.lock = threading.RLock()

    def list_sessions(self, app_id):
        with self.lock, closing(sqlite3.connect(self.db_path)) as db, db:
            rows = db.execute("SELECT id,messages FROM sessions WHERE app_id=? ORDER BY rowid DESC", (app_id,)).fetchall()
        return [{"id": sid, "title": (json.loads(messages)[0]["content"] or
                    ', '.join(item['name'] for item in json.loads(messages)[0].get('attachments', [])))[:70]}
                for sid, messages in rows]

    def get_session(self, app_id, session_id):
        with self.lock, closing(sqlite3.connect(self.db_path)) as db, db:
            row = db.execute("SELECT messages FROM sessions WHERE id=? AND app_id=?", (session_id, app_id)).fetchone()
        if not row:
            raise ValueError("Conversation not found")
        messages=json.loads(row[0])
        for message in messages:
            if message.get('attachments'):
                message['attachments']=public_attachments(message['attachments'])
        return {"id": session_id, "messages": messages}

    def configuration(self, app):
        validate(app)
        blockers = [i["message"] for i in analyze(app)["issues"] if i["severity"] == "blocker"]
        if blockers:
            raise ValueError("Unresolved configuration: " + " ".join(blockers))
        model = app["runtime"].get("model") or os.environ.get("OPENAI_MODEL")
        if not model:
            raise ValueError("Set OPENAI_MODEL or runtime.model to an available model supporting the selected tools")
        tools = []
        for kind in app["runtime"]["hosted_tools"]:
            tool = {"type": kind}
            if kind == "code_interpreter":
                tool["container"] = {"type": "auto"}
            tools.append(tool)
        if app["bindings"]["vector_store_ids"]:
            tools.append({"type": "file_search", "vector_store_ids": app["bindings"]["vector_store_ids"]})
        names = set(app["bindings"]["function_tools"]) | set(app["bindings"]["action_tools"].values())
        for name in sorted(names):
            tool = self.registry.tools.get(name)
            if not tool:
                raise ValueError(f"Backend tool {name} is not registered")
            if not tool.read_only:
                raise ValueError(f"Tool {name} requires an approval/idempotency adapter; write tools are disabled in this starter")
            tools.append(tool.declaration())
        return model, tools, names

    def model_response(self, payload, emit):
        if emit is None:
            return self.client.create(payload)
        emit({"type": "reset"})
        statuses = {
            "response.web_search_call.in_progress": "Searching the web…",
            "response.file_search_call.in_progress": "Searching knowledge files…",
            "response.code_interpreter_call.in_progress": "Running code…",
            "response.image_generation_call.in_progress": "Generating an image…",
        }
        # Closing on callback/disconnect errors cancels the upstream stream too.
        with closing(self.client.stream(payload)) as events:
            for event in events:
                kind = event.get("type")
                if kind in ("response.output_text.delta", "response.refusal.delta"):
                    delta = event.get("delta")
                    if isinstance(delta, str):
                        index, part = event.get("output_index", 0), event.get("content_index", 0)
                        if type(index) is not int or type(part) is not int or index < 0 or part < 0:
                            raise ValueError("OpenAI returned invalid streaming text indices")
                        emit({"type": "delta", "delta": delta, "output_index": index, "content_index": part})
                elif kind in statuses:
                    emit({"type": "status", "message": statuses[kind]})
                elif kind in ("response.completed", "response.incomplete", "response.failed"):
                    result = event.get("response")
                    if not isinstance(result, dict) or result.get("status") != kind.removeprefix("response."):
                        raise ValueError("OpenAI returned an invalid terminal response; no conversation turn was saved")
                    return result
                elif kind == "error":
                    raise ValueError("OpenAI response was incomplete or failed; no conversation turn was saved")
        raise ValueError("OpenAI stream ended before completion; no conversation turn was saved")

    def chat(self, app, message, session_id=None, emit=None, attachments=None):
        files=validate_attachments(attachments)
        if not isinstance(message, str) or (not message.strip() and not files) or len(message) > 16000:
            raise ValueError("Message must contain 1–16000 characters")
        model, tools, allowed = self.configuration(app)
        fingerprint = hashlib.sha256((json.dumps(app, sort_keys=True) + model).encode()).hexdigest()
        with self.lock:
            history = []
            if session_id:
                with closing(sqlite3.connect(self.db_path)) as db, db:
                    row = db.execute("SELECT app_id,fingerprint,messages FROM sessions WHERE id=?", (session_id,)).fetchone()
                if not row or row[0] != app["id"]:
                    raise ValueError("Conversation does not belong to this application")
                if row[1] != fingerprint:
                    raise ValueError("Application configuration changed; start a new conversation")
                history = json.loads(row[2])
            if len(history) >= 80 or sum(len(m["content"]) for m in history) + len(message) > 160000:
                raise ValueError("Conversation limit reached; start a new conversation")
            attachment_bytes=sum(item['size'] for m in history for item in m.get('attachments',[]))
            if attachment_bytes+sum(item['size'] for item in files)>MAX_ATTACHMENT_BYTES:
                raise ValueError('Conversation attachment limit reached (20 MiB); start a new conversation')
            # Only the application developer config becomes instructions; user text/files remain user input.
            working = [{"role": m["role"], "content": input_content(m["content"],m.get('attachments',[]))} for m in history]
            working.append({"role": "user", "content": input_content(message,files)})
            assets, citations, usage = [], [], []
            for round_number in range(app["runtime"]["max_tool_rounds"] + 1):
                payload = {"model": model, "instructions": app["instructions"], "input": working,
                           "store": False, "max_output_tokens": app["runtime"]["max_output_tokens"]}
                if tools:
                    payload["tools"] = tools
                if app["runtime"].get("output_schema"):
                    payload["text"] = {"format": {"type": "json_schema", "name": "app_output", "strict": True,
                                                   "schema": app["runtime"]["output_schema"]}}
                response = self.model_response(payload, emit)
                details = response.get("incomplete_details")
                length_limited = (response.get("status") == "incomplete" and isinstance(details, dict)
                                  and details.get("reason") == "max_output_tokens")
                if response.get("status") != "completed" and not length_limited:
                    raise ValueError(response_failure_message(response, payload["max_output_tokens"]))
                usage.append(response.get("usage", {}))
                output = response.get("output", [])
                calls = [item for item in output if item.get("type") == "function_call"]
                if length_limited:
                    visible_text = any(part.get("type") == "output_text" and part.get("text", "").strip()
                                       for item in output if item.get("type") == "message"
                                       for part in item.get("content", []))
                    # Never treat a truncated JSON result or function arguments as valid output.
                    if not visible_text or calls or app["runtime"].get("output_schema"):
                        raise ValueError(response_failure_message(response, payload["max_output_tokens"]))
                for item in output:
                    if not length_limited and item.get("type") == "image_generation_call" and item.get("result"):
                        raw = base64.b64decode(item["result"], validate=True)
                        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                            extension = "png"
                        elif raw.startswith(b"\xff\xd8\xff"):
                            extension = "jpg"
                        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
                            extension = "webp"
                        else:
                            raise ValueError("Unsupported generated image format")
                        name = f"{uuid.uuid4().hex}.{extension}"
                        (self.assets / name).write_bytes(raw)
                        assets.append(name)
                    if item.get("type") == "message":
                        for part in item.get("content", []):
                            for annotation in part.get("annotations", []):
                                kind = annotation.get("type")
                                if kind == "url_citation":
                                    citations.append({"title": annotation.get("title", "Source"), "url": annotation.get("url", "")})
                                elif kind == "file_citation":
                                    citations.append({"title": annotation.get("filename", "Knowledge file"), "file_id": annotation.get("file_id")})
                if not calls:
                    chunks = []
                    for item in output:
                        if item.get("type") == "message":
                            for part in item.get("content", []):
                                if part.get("type") == "output_text":
                                    chunks.append(part.get("text", ""))
                                elif part.get("type") == "refusal":
                                    chunks.append(part.get("refusal", ""))
                    answer = "\n".join(chunks)
                    if not answer and not assets:
                        raise ValueError("No displayable text or image returned")
                    session_id = session_id or uuid.uuid4().hex
                    assistant = {"role": "assistant", "content": answer or "[Generated image]",
                                 "assets": assets, "citations": citations}
                    if length_limited:
                        assistant["incomplete_reason"] = "max_output_tokens"
                    user={"role": "user", "content": message}
                    if files:
                        user['attachments']=files
                    history.extend([user, assistant])
                    with closing(sqlite3.connect(self.db_path)) as db, db:
                        db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)", (session_id, app["id"], fingerprint, json.dumps(history)))
                    return {"session_id": session_id, "message": assistant, "usage": usage}
                if round_number == app["runtime"]["max_tool_rounds"]:
                    raise ValueError("Function-call round limit reached; no conversation turn was saved")
                if emit is not None:
                    emit({"type": "status", "message": "Running backend tools…"})
                working.extend(copy.deepcopy(output))
                for call in calls:
                    if call.get("name") not in allowed:
                        raise ValueError("Model requested an unapproved backend tool")
                    arguments = json.loads(call["arguments"])
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be an object")
                    # Registered handlers must independently validate all inputs.
                    result = self.registry.tools[call["name"]].handler(**arguments)
                    working.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)})
