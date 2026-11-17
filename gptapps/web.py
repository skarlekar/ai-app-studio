"""Local single-user HTTP application. Deploy behind authentication for shared use."""
import json
import re
import os
import mimetypes
import io
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote

from .attachments import MAX_REQUEST_BYTES, MAX_FILES as CHAT_MAX_FILES, MAX_FILE_BYTES as CHAT_MAX_FILE_BYTES, MAX_TOTAL_BYTES as CHAT_MAX_TOTAL_BYTES, EXTENSIONS as CHAT_EXTENSIONS
from .spec import analyze, load, from_chat_input
from .runtime import Runtime
from .build import build_app
from .version import build_info
from .setup import SetupInterpreter
from .knowledge import KnowledgeManager, MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES, EXTENSIONS


def serve(apps_path, data_dir, port=8765, registry=None, builder=False, host="127.0.0.1", agents_client=None):
    if builder and not Path(apps_path).is_dir():
        raise ValueError("Conversational setup requires an apps directory")
    paths = [apps_path] if Path(apps_path).is_file() else sorted(Path(apps_path).glob("*.json"))
    apps, app_paths = {}, {}
    for path in paths:
        app = load(path)
        if app["id"] in apps:
            raise ValueError("Duplicate application ID")
        apps[app["id"]] = app
        app_paths[app["id"]] = Path(path)
    if not apps and not builder:
        raise ValueError("No application specs found")
    runtime = Runtime(data_dir, registry=registry, **({"agents_client":agents_client} if agents_client is not None else {}))
    setup = SetupInterpreter(client=runtime.client) if builder else None
    knowledge = KnowledgeManager(data_dir) if builder else None
    html = Path(__file__).with_name("chat.html").read_bytes()
    static = {"/static/workshop.js": Path(__file__).with_name("workshop.js"),
              "/static/workshop.css": Path(__file__).with_name("workshop.css"),
              "/static/routing.js": Path(__file__).with_name("routing.js"),
              "/static/routing.css": Path(__file__).with_name("routing.css"),
              "/static/attachments.js": Path(__file__).with_name("attachments.js"),
              "/static/chat.js": Path(__file__).with_name("chat.js"),
              "/static/knowledge.js": Path(__file__).with_name("knowledge.js"),
              "/static/chat.css": Path(__file__).with_name("chat.css"),
              "/static/vendor/marked.umd.js": Path(__file__).with_name("vendor") / "marked.umd.js",
              "/static/vendor/purify.min.js": Path(__file__).with_name("vendor") / "purify.min.js"}
    for name in ("plus", "download", "history", "arrow-up", "arrow-up-right", "chevron-down", "lock-keyhole", "layers"):
        static[f"/static/icons/{name}.svg"] = Path(__file__).with_name("icons") / f"{name}.svg"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid logging query strings or conversation text.

        def send(self, code, data, content_type="application/json", headers=None):
            raw = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)

        def valid_request(self):
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                self.send(403, {"error": "Invalid host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in hosts}:
                self.send(403, {"error": "Cross-origin requests are disabled"})
                return False
            return True

        def do_GET(self):
            if not self.valid_request():
                return
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                return self.send(200, html, "text/html; charset=utf-8")
            if url.path in static:
                kind = "image/svg+xml" if url.path.endswith(".svg") else "text/css" if url.path.endswith(".css") else "text/javascript"
                return self.send(200, static[url.path].read_bytes(), kind + "; charset=utf-8")
            if url.path == "/api/apps":
                from .evaluation import release_gate
                def evaluation_status(app):
                    path=Path(data_dir)/'evaluations'/(app['id']+'.json')
                    try:return release_gate(app,json.loads(path.read_text()))
                    except (ValueError,OSError):return {'approved':False,'status':'release_hold','reasons':['Task-specific evaluation and human review are required before production.']}
                return self.send(200, [{"id": a["id"], "name": a["name"], "description": a["description"],
                    "starters": a["conversation_starters"], "evaluation":evaluation_status(a), "runtime": {"api":a["runtime"]["api"],"model":a["runtime"].get("model"),"environment":a["runtime"].get("agents",{}).get("environment")}, "report": analyze(a)} for a in apps.values()])
            if url.path == "/api/config":
                config = {"builder_enabled": builder, **build_info(), "chat_attachments": {"max_files": CHAT_MAX_FILES,
                    "max_file_bytes": CHAT_MAX_FILE_BYTES,"max_total_bytes": CHAT_MAX_TOTAL_BYTES,"extensions": CHAT_EXTENSIONS}}
                from .agents_client import sdk_available
                config['runtimes'] = {'responses':{'available':True}, 'agents':{
                    'available':agents_client is not None or sdk_available(), 'fixed_only':True,
                    'environments':['openai_hosted','none'], 'provider_access':'not_verified'}}
                if builder:
                    try:
                        from .routing import load_policy_file
                        load_policy_file();config['routing_available']=True
                    except (ValueError,OSError):
                        config['routing_available']=False
                        config['routing_error']='Auto routing needs a valid server model policy. See the README routing setup.'
                    config["knowledge_uploads"] = {"max_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES,
                                                   "max_total_bytes": MAX_TOTAL_BYTES, "extensions": EXTENSIONS}
                return self.send(200, config)
            if url.path == '/api/runs' or url.path.startswith('/api/runs/') or url.path.startswith('/api/artifacts/') or url.path == '/api/sources':
                app_id=query.get('app',[''])[0]
                if app_id not in apps:
                    return self.send(404, {'error':'Application not found'})
                try:
                    store=runtime.managed_store()
                    if url.path == '/api/runs':
                        return self.send(200, store.find_submission(app_id, query.get('submission_id',[''])[0]))
                    match=re.fullmatch(r'/api/runs/([a-f0-9]{32})(/events)?',url.path)
                    if match:
                        run=store.get(app_id,match[1])
                        if not match[2]:return self.send(200,run)
                        after=int(query.get('after',['0'])[0])
                        if not 0<=after<=2**63-1:raise ValueError('Invalid event cursor')
                        self.send_response(200)
                        self.send_header('Content-Type','text/event-stream; charset=utf-8')
                        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                        self.send_header('Connection','close');self.end_headers();self.close_connection=True
                        try:
                            for event in runtime.managed.observe(app_id,run['id'],after):
                                self.wfile.write(('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                        return
                    match=re.fullmatch(r'/api/artifacts/([a-f0-9]{32})/content',url.path)
                    if match:
                        artifact=store.artifact_content(app_id,match[1])
                        return self.send(200,artifact['path'].read_bytes(),'application/octet-stream',
                            {'Content-Disposition':"attachment; filename*=UTF-8''"+quote(artifact['name'],safe='')})
                    if url.path == '/api/sources':
                        run=store.get(app_id,query.get('run',[''])[0]);source_id=query.get('source',[''])[0]
                        source=next((s for s in run.get('sources',[]) if s['id']==source_id),None)
                        if not source:raise ValueError('Source not found or expired')
                        return self.send(200,source)
                    return self.send(404,{'error':'Not found'})
                except (ValueError,TypeError):return self.send(404,{'error':'Run, artifact or source not found for this application'})
            if url.path in ("/api/knowledge", "/api/knowledge/status"):
                if not builder:
                    return self.send(403, {"error": "Knowledge uploads are disabled in this standalone app"})
                try:
                    result = knowledge.list() if url.path == "/api/knowledge" else knowledge.get(query.get("id", [None])[0], refresh=True)
                    return self.send(200, result)
                except ValueError as error:
                    return self.send(400, {"error": str(error)})
            if url.path == "/api/spec" and builder:
                app_id = query.get("app", [""])[0]
                if app_id not in apps:
                    return self.send(404, {"error": "Unknown application"})
                return self.send(200, apps[app_id])
            if url.path == "/api/build" and builder:
                app_id = query.get("app", [""])[0]
                if app_id not in apps:
                    return self.send(404, {"error": "Unknown application"})
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp) / "application"
                    build_app(apps[app_id], root)
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                        for file in sorted(root.rglob("*")):
                            if file.is_file():
                                archive.write(file, file.relative_to(root))
                return self.send(200, buffer.getvalue(), "application/zip")
            if url.path == "/api/sessions":
                app_id = query.get("app", [""])[0]
                if app_id not in apps:
                    return self.send(404, {"error": "Unknown application"})
                sid = query.get("id", [None])[0]
                try:
                    return self.send(200, runtime.get_session(app_id, sid) if sid else runtime.list_sessions(app_id))
                except ValueError:
                    return self.send(404, {"error": "Conversation not found"})
            if url.path.startswith("/assets/"):
                filename = url.path.removeprefix("/assets/")
                if "/" in filename or "\\" in filename or filename.startswith("."):
                    return self.send(404, {"error": "Not found"})
                asset = runtime.assets / filename
                if asset.is_file():
                    return self.send(200, asset.read_bytes(), mimetypes.guess_type(filename)[0] or "application/octet-stream")
            self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_request():
                return
            url = urlparse(self.path)
            path = url.path
            knowledge_paths = ("/api/knowledge", "/api/knowledge/file", "/api/knowledge/index", "/api/knowledge/bind")
            if path not in ("/api/chat", "/api/apps", "/api/setup", "/api/runs", "/api/runtime/check", "/api/sessions/cleanup", *knowledge_paths) and not re.fullmatch(r"/api/runs/[a-f0-9]{32}/(?:cancel|reconcile)",path):
                return self.send(404, {"error": "Not found"})
            if path in knowledge_paths and not builder:
                return self.send(403, {"error": "Knowledge uploads are disabled in this standalone app"})
            binary = path == "/api/knowledge/file"
            if self.headers.get("Content-Type", "").split(";")[0] != ("application/octet-stream" if binary else "application/json"):
                return self.send(415, {"error": "JSON body required"})
            streaming = False

            def event(data):
                nonlocal streaming
                if not streaming:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Accel-Buffering", "no")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    streaming = True
                self.wfile.write(("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode())
                self.wfile.flush()

            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= (MAX_FILE_BYTES if binary else MAX_REQUEST_BYTES if path in ("/api/chat","/api/setup","/api/runs") else 1500000):
                    raise ValueError("Invalid request size")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body")
                if binary:
                    query = parse_qs(url.query)
                    slot = query.get("index", [""])[0]
                    if not slot.isascii() or not slot.isdigit() or len(slot) > 3:
                        raise ValueError("Invalid knowledge file index")
                    return self.send(200, knowledge.upload(query.get("id", [None])[0], int(slot), raw))
                body = json.loads(raw)
                if path in knowledge_paths:
                    if not isinstance(body, dict):
                        raise ValueError("Knowledge request must be an object")
                    if path == "/api/knowledge":
                        return self.send(201, knowledge.start(body.get("files")))
                    if path == "/api/knowledge/index":
                        return self.send(200, knowledge.index(body.get("upload_id")))
                    app_id = body.get("app_id")
                    if not isinstance(app_id, str) or app_id not in apps:
                        raise ValueError("Unknown application")
                    with runtime.lock:
                        updated = knowledge.apply(body.get("upload_id"), apps[app_id])
                        destination = app_paths[app_id]
                        if load(destination) != apps[app_id]:
                            raise ValueError("Application configuration changed on disk; restart the server before binding knowledge")
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as file:
                            temporary = Path(file.name)
                            try:
                                json.dump(updated, file, ensure_ascii=False, indent=2)
                                file.write("\n")
                                file.close()
                                temporary.replace(destination)
                            finally:
                                temporary.unlink(missing_ok=True)
                        apps[app_id] = updated
                        knowledge.claim(body.get("upload_id"), app_id)
                    return self.send(200, {"id": app_id, "report": analyze(updated)})
                if path == '/api/runtime/check':
                    if not builder:return self.send(403,{'error':'Setup is disabled'})
                    app=from_chat_input(body);report=analyze(app)
                    if app['runtime']['api']=='agents':runtime.managed.configuration(app)
                    from .agents_client import sdk_available
                    return self.send(200,{'report':report,'sdk_available':agents_client is not None or sdk_available(),
                        'credentials_present':bool(os.environ.get('OPENAI_API_KEY')),'provider_access':'not_verified'})
                if path == '/api/runs' or re.fullmatch(r'/api/runs/[a-f0-9]{32}/(?:cancel|reconcile)',path) or path == '/api/sessions/cleanup':
                    if not isinstance(body,dict) or body.get('app_id') not in apps:raise ValueError('Unknown application')
                    app=apps[body['app_id']]
                    if app['runtime']['api']!='agents':raise ValueError('This route requires the Agents runtime')
                    if path == '/api/runs':
                        run=runtime.managed.start(app,body.get('message'),body.get('session_id'),body.get('submission_id'),body.get('attachments'))
                        return self.send(202,run)
                    if path == '/api/sessions/cleanup':
                        if body.get('confirm') is not True:raise ValueError('Explicit cleanup confirmation is required')
                        return self.send(200,runtime.managed.cleanup(app['id'],body.get('session_id')))
                    run_id=path.split('/')[3]
                    result=runtime.managed.cancel(app['id'],run_id) if path.endswith('/cancel') else runtime.managed.reconcile(app['id'],run_id)
                    return self.send(200,result)
                if path == "/api/setup":
                    if not builder:
                        return self.send(403, {"error": "Application setup is disabled in this standalone app"})
                    if not isinstance(body, dict):
                        raise ValueError("Setup request must be an object")
                    return self.send(200, setup.interpret(body.get("field"), body.get("message"), body.get("history"), attachments=body.get("attachments"), runtime_api=body.get("runtime_api","responses")))
                if path == "/api/apps":
                    if not builder:
                        return self.send(403, {"error": "Application setup is disabled in this standalone app"})
                    app = from_chat_input(body)
                    upload_id = body.get("knowledge_upload_id")
                    if upload_id is not None:
                        app = knowledge.apply(upload_id, app)
                    path = Path(apps_path) / f"{app['id']}.json"
                    with runtime.lock:
                        with path.open("x") as file:
                            file.write(json.dumps(app, ensure_ascii=False, indent=2) + "\n")
                        path.chmod(0o600)
                        apps[app["id"]] = app
                        app_paths[app["id"]] = path
                        if upload_id is not None:
                            knowledge.claim(upload_id, app["id"])
                    return self.send(201, {"id": app["id"], "name": app["name"], "report": analyze(app)})
                if not isinstance(body, dict) or body.get("app_id") not in apps:
                    raise ValueError("Unknown application")
                sid = body.get("session_id")
                if sid is not None and (not isinstance(sid, str) or len(sid) > 128):
                    raise ValueError("Invalid conversation ID")
                if type(body.get("stream", False)) is not bool:
                    raise ValueError("stream must be a boolean")
                if body.get("stream"):
                    result = runtime.chat(apps[body["app_id"]], body.get("message"), sid, emit=event, attachments=body.get("attachments"), submission_id=body.get("submission_id"))
                    event({"type": "done", **result})
                else:
                    result = runtime.chat(apps[body["app_id"]], body.get("message"), sid, attachments=body.get("attachments"), submission_id=body.get("submission_id"))
                    self.send(200, result)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # A disconnected client must not trigger a second response or keep its model stream open.
            except (ValueError, TypeError) as exc:
                # Known setup/validation errors only. Extension handlers should use ValueError without secrets.
                if streaming:
                    try:
                        event({"type": "error", "error": str(exc)})
                    except OSError:
                        pass
                else:
                    self.send(400, {"error": str(exc)})
            except Exception:
                error = "Request failed; completion could not be confirmed. Check saved conversations before retrying."
                if streaming:
                    try:
                        event({"type": "error", "error": error})
                    except OSError:
                        pass
                else:
                    self.send(500, {"error": error})

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Open http://127.0.0.1:{port} — {len(apps)} application(s). Press Ctrl+C to stop.", flush=True)
    try:
        if any(a['runtime']['api']=='agents' for a in apps.values()) and (Path(data_dir)/'managed.sqlite3').exists():
            runtime.managed.recover()
            runtime.managed.maintenance()
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()
