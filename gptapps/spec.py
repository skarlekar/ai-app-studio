"""Versioned application configuration. Imported instructions are data, never code."""
import hashlib
import json
import re
from pathlib import Path

VERSION = "1.0"
CAPABILITIES = {
    "web_search": "web_search",
    "image_generation": "image_generation",
    "code_interpreter_and_data_analysis": "code_interpreter",
}


def validate(app):
    if app.get("schema_version") != VERSION:
        raise ValueError("Unsupported application schema version")
    for key in ("id", "name", "instructions"):
        if not isinstance(app.get(key), str) or not app[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}", app["id"]):
        raise ValueError("Application id must be a safe filename")
    if not isinstance(app.get("conversation_starters", []), list) or any(
        not isinstance(s, str) for s in app.get("conversation_starters", [])
    ):
        raise ValueError("conversation_starters must be a list of strings")
    runtime = app.get("runtime", {})
    if runtime.get("api") != "responses":
        raise ValueError("This runtime supports the Responses API")
    if runtime.get("model") is not None and not isinstance(runtime["model"], str):
        raise ValueError("model must be a string or null")
    schema = runtime.get("output_schema")
    if schema is not None and (not isinstance(schema, dict) or schema.get("type") != "object"):
        raise ValueError("output_schema must be an object JSON Schema or null")
    tools = runtime.get("hosted_tools", [])
    if not isinstance(tools, list) or any(t not in CAPABILITIES.values() for t in tools):
        raise ValueError("Unsupported hosted tool; add a reviewed runtime adapter")
    for key in ("max_output_tokens", "max_tool_rounds"):
        value = runtime.get(key)
        if type(value) is not int or not 1 <= value <= (131072 if key == "max_output_tokens" else 10):
            raise ValueError(f"Invalid runtime.{key}")
    bindings = app.get("bindings", {})
    for key in ("vector_store_ids", "function_tools"):
        if not isinstance(bindings.get(key, []), list) or any(
            not isinstance(s, str) for s in bindings.get(key, [])
        ):
            raise ValueError(f"bindings.{key} must be a list of strings")
    action_map = bindings.get("action_tools", {})
    if not isinstance(action_map, dict) or any(not isinstance(v, str) for v in action_map.values()):
        raise ValueError("bindings.action_tools must map action IDs to tool names")
    return app


def load(path):
    return validate(json.loads(Path(path).read_text()))


def import_export(document):
    entries = document.get("gpts") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("Expected a nonempty gpts array in the owner-provided export")
    apps, seen = [], set()
    for entry in entries:
        source_id = entry.get("id")
        if not isinstance(source_id, str) or source_id in seen:
            raise ValueError("Each source GPT requires a unique string id")
        seen.add(source_id)
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "-", source_id)[:100]
        safe_id += "-" + hashlib.sha256(source_id.encode()).hexdigest()[:8]
        items = entry.get("capabilities", {}).get("items")
        if not isinstance(items, list) or any(
            not isinstance(c, dict) or not isinstance(c.get("key"), str) or type(c.get("enabled")) is not bool for c in items
        ):
            raise ValueError("Each GPT needs explicit capabilities.items with string keys and boolean enabled values")
        enabled = [c["key"] for c in items if c.get("enabled") is True]
        files = entry.get("knowledge", {}).get("files", [])
        # Record file inventory and action IDs only; never copy authentication objects.
        file_names = [f if isinstance(f, str) else f.get("name", f.get("filename", "unnamed")) for f in files]
        actions = entry.get("actions", {})
        action_count = max(actions.get("count", 0), len(actions.get("items", [])))
        app = {
            "schema_version": VERSION,
            "id": safe_id,
            "name": entry.get("name"),
            "description": entry.get("description", ""),
            "instructions": entry.get("instructions"),
            "conversation_starters": entry.get("conversation_starters", []),
            "source": {"type": "custom_gpt_export", "id": source_id},
            "runtime": {"api": "responses", "model": None,
                        "hosted_tools": list(dict.fromkeys(CAPABILITIES[k] for k in enabled if k in CAPABILITIES)),
                        "max_output_tokens": 16384, "max_tool_rounds": 4, "output_schema": None},
            "bindings": {"vector_store_ids": [], "function_tools": [], "action_tools": {}},
            "requirements": {"knowledge_files": file_names,
                             "actions": [f"action-{i+1}" for i in range(action_count)],
                             "unsupported_capabilities": [k for k in enabled if k not in CAPABILITIES]},
        }
        apps.append(validate(app))
    return apps


def analyze(app):
    """Heuristic suggestions are separate from deterministic blockers."""
    validate(app)
    issues = []
    req, bindings = app.get("requirements", {}), app["bindings"]
    if req.get("knowledge_files") and not bindings["vector_store_ids"]:
        issues.append({"severity": "blocker", "code": "knowledge_unbound", "message":
                       "Upload/index the knowledge files and bind vector_store_ids; files were not imported."})
    for action in req.get("actions", []):
        if action not in bindings["action_tools"]:
            issues.append({"severity": "blocker", "code": "action_unbound", "message":
                           f"Bind {action} to a reviewed backend tool. Action schemas/auth were not imported."})
    for capability in req.get("unsupported_capabilities", []):
        issues.append({"severity": "blocker", "code": "capability_unsupported", "message":
                       f"Add an adapter for {capability}."})
    text = app["instructions"].lower()
    tools = app["runtime"]["hosted_tools"]
    checks = [
        ("image_generation" not in tools and bool(re.search(r"generat\w* (?:and display )?(?:a |an |one |new )?image", text)),
         "image_tool_missing", "Instructions appear to require image generation, but it is disabled."),
        ("cosine similarity" in text, "scoring_extension", "Use embeddings and code for real cosine scoring; text similarity is not image similarity."),
        ("longest word" in text or "longest words" in text, "rules_extension", "Use a dictionary/search algorithm and rule validator for exact longest-word claims."),
        ("citations" in text or "citing verses" in text, "source_verification", "Consider verified source retrieval to substantiate quotations and citations."),
        ("audio" in text or "pronunciation" in text, "audio_extension", "Audio/voice behavior needs a separate audio or Realtime adapter; this template provides text chat."),
        ("d3.js" in text or "network graph" in text, "graph_extension", "Add structured output validation and a graph renderer; this template displays chat text."),
    ]
    issues.extend({"severity": "review", "code": code, "message": message, "heuristic": True}
                  for match, code, message in checks if match)
    return {"id": app["id"], "name": app["name"],
            "runtime_ready": not any(i["severity"] == "blocker" for i in issues),
            "behavior_review_required": any(i["severity"] == "review" for i in issues),
            "issues": issues}


def from_chat_input(draft):
    """Collect a reviewed conversational draft without executing its Action schemas."""
    import uuid
    if not isinstance(draft, dict):
        raise ValueError("Application draft must be an object")
    for key, limit, required in (("name", 200, True), ("description", 2000, False), ("instructions", 32000, True)):
        value = draft.get(key, "")
        if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
            raise ValueError(f"Invalid {key}; maximum {limit} characters")
    starters = draft.get("starters", [])
    if not isinstance(starters, list) or len(starters) > 12 or any(not isinstance(s, str) or len(s) > 500 for s in starters):
        raise ValueError("Provide up to 12 conversation starters, each at most 500 characters")
    tools = draft.get("tools", [])
    if not isinstance(tools, list) or any(t not in CAPABILITIES.values() for t in tools):
        raise ValueError("Choose supported tool settings")
    files = draft.get("knowledge_files", [])
    if not isinstance(files, list) or len(files) > 100 or any(not isinstance(f, str) or len(f) > 300 for f in files):
        raise ValueError("Invalid knowledge file inventory")
    # Older setup clients can submit an absence reply as a single filename.
    # Match the entire reply, so actual filenames and mixed inventories survive.
    if len(files) == 1 and re.fullmatch(
        r"(?:none|no|skip|default|n/a|no (?:knowledge )?files(?: (?:needed|required))?)[.!]?",
        " ".join(files[0].lower().split()),
    ):
        files = []
    model = draft.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 128):
        raise ValueError("Invalid model setting")
    actions = draft.get("actions", [])
    if not isinstance(actions, list) or len(actions) > 20:
        raise ValueError("Provide at most 20 Action definitions")
    definitions = []
    secret_keys = {"api_key", "apikey", "client_secret", "access_token", "refresh_token", "password", "authorization"}

    def reject_secrets(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in secret_keys and isinstance(item, str) and item.strip():
                    raise ValueError("Remove credential values from the Action schema; keep only schema definitions")
                reject_secrets(item)
        elif isinstance(value, list):
            for item in value:
                reject_secrets(item)
        elif isinstance(value, str) and re.search(r"\bsk-[A-Za-z0-9_-]{16,}|\bBearer\s+[A-Za-z0-9._~-]{12,}", value):
            raise ValueError("Remove apparent credentials from the Action schema")

    for index, action in enumerate(actions):
        if not isinstance(action, dict) or set(action) - {"name", "auth_type", "schema"}:
            raise ValueError("Actions accept only name, auth_type and schema; no credential fields")
        name, auth, schema = action.get("name"), action.get("auth_type"), action.get("schema")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Each Action needs a name")
        if auth not in ("none", "api_key", "oauth"):
            raise ValueError("Action auth_type must be none, api_key or oauth")
        if not isinstance(schema, dict) or not schema:
            raise ValueError("Each Action needs an OpenAPI schema as a nonempty JSON object")
        if len(json.dumps(schema)) > 64000:
            raise ValueError("Action schema exceeds 64000 characters")
        reject_secrets(schema)
        definitions.append({"id": f"action-{index+1}", "name": name, "auth_type": auth, "schema": schema})
    entry = {"id": "chat-" + uuid.uuid4().hex, "name": draft["name"].strip(),
             "description": draft.get("description", ""), "instructions": draft["instructions"],
             "conversation_starters": starters,
             "capabilities": {"items": [{"key": key, "enabled": value in tools} for key, value in CAPABILITIES.items()]},
             "knowledge": {"files": files}, "actions": {"count": len(definitions)}}
    app = import_export({"gpts": [entry]})[0]
    app["source"]["type"] = "conversational_setup"
    app["runtime"]["model"] = model
    app["action_definitions"] = definitions
    return validate(app)
