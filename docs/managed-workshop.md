# Beyond the Dispatch Desk: Giving AI Applications a Managed Workshop

Version 0.3.0 adds an explicit **Agents API** runtime alongside the existing **Responses API** runtime. Both use the same Studio setup, chat interface, attachment intake, local history, export and build label. This is an experimental local application, with a separate behavioral evaluation gate for production decisions.

## Choose who manages the work

| Choice | Execution | Model policy | Useful starting point |
| --- | --- | --- | --- |
| Responses (default) | Studio owns requests, tool rounds and history | Fixed or Decisions-based Auto | Chat, fast answers, image generation, existing structured outputs |
| Agents (opt-in) | OpenAI manages a persistent session and turn; Studio supervises and records it | Explicit fixed model only | Multi-step research, document work and downloadable deliverables |

Adding knowledge or Actions never changes runtimes automatically. **Suggest runtime with AI** proposes a choice; the owner confirms it. It is not the Decisions classifier. Agents API is a hosted execution API; this implementation uses the official **OpenAI Python SDK**, not the separate Agents SDK caller-owned loop or the Workspace Agents API.

## Start Studio

```sh
./start.sh --agents
# Or, with Python supplied by Docker:
./docker-start.sh --agents
```

The local launcher creates `.venv-agents` and installs `openai==3.13.0` there. Override the directory with `GPTAPPS_AGENTS_VENV`. The Docker flag installs that SDK in the image using `WITH_AGENTS=1`. Normal launches keep the Responses dependency-free default. Manual installation: `python3 -m pip install '.[agents]'` in a virtual environment.

Use the existing server-side `OPENAI_API_KEY`; never place it in an app manifest, chat, or sandbox. Studio setup still needs `OPENAI_SETUP_MODEL` or `OPENAI_MODEL` supporting Responses Structured Outputs. Agents needs an application API key with `api.agents.read`, `api.agents.write` and `api.responses.write`, plus permission for the selected tools and knowledge project. OpenAI's [quickstart](https://developers.openai.com/api/docs/guides/agents-api/quickstart) currently demonstrates `gpt-6-astra`; verify availability, cost and behavior in your own project. A configuration check does not make a paid request or verify live access.

In setup, select **Agents API**, enter the fixed model ID, and select the working environment. `Auto` and an implicit server-default model are rejected for Agents. Review the original instructions and tool bindings before creating the app.

## Manifest example

Use `from_chat_input` to create a complete manifest rather than guessing the rest of its schema:

```python
import json
from gptapps.spec import from_chat_input

app = from_chat_input({
    "name": "Research Workshop",
    "description": "Produce evidence-based briefings and reviewable deliverables.",
    "instructions": "Answer clearly, identify uncertainty, and create a summary file when requested.",
    "api": "agents",
    "model": "gpt-6-astra",
    "agents": {"environment": "openai_hosted", "max_run_seconds": 300,
               "max_application_tool_calls": 12, "artifact_retention_days": 7}
})
with open("workshop.json", "x") as file:
    json.dump(app, file, indent=2)
```

Agents uses schema `2.0`. Legacy schema `1.0` Responses manifests retain their behavior. `network_access=disabled`, `review=auto_review` and `tool_policy=read_only` are enforced. One agent runs per session; multi-agent delegation is disabled. The hosted workspace can execute code and create local files even though external business tools are read-only. `none` has no filesystem: chat attachments and Code Interpreter requests are blocked. Image generation and strict output schemas require the Responses adapter in this release.

## Task lifecycle and recovery

The browser submits a stable ID to `POST /api/runs` and receives a run identity promptly. A Python supervisor works independently of the SSE observer. The task timeline shows accepted, preparing, running, finalizing and completed states; failures, reconnecting, cancelling and unresolved outcomes remain explicit.

SQLite records intent before submission, provider IDs, the intended root turn, monotonic public events, tool results and output metadata. Reusing an ID with identical input returns its existing run. Conflicting reuse and a second active/unresolved task in the same conversation are rejected. A changed app configuration or knowledge inventory requires a new conversation.

Reloading or opening a saved conversation reattaches to saved work. **Leave task running** detaches the browser only. **Cancel task** requests provider cancellation and reports it as confirmed only after checking provider state. The configured deadline also requests cancellation. Keep one server process per data directory; an OS lock prevents multiple supervisors.

On restart, queued unsent work can start; known provider sessions are reconciled. An initial submission that may have reached OpenAI but has no saved provider session ID is **not automatically resent**. Use **Reconcile saved status** where an ID is known. For an unknown session, inspect OpenAI project logs using the local run ID in session metadata. Do not assume another submission is free or duplicate-safe. Idempotency reduces duplicate work; this is not an exactly-once guarantee.

The server must remain running for active supervision, deadlines and cleanup retries. Closing the server is not a claim that provider work stopped. On restart it recovers saved work. This is a single-process local runtime, not a highly available job service.

## Knowledge, tools, inputs and outputs

Permanent knowledge still uploads through the Studio Files/Vector Stores workflow. Responses declares hosted `file_search`. Agents exposes an application-owned `search_knowledge` function that searches **only the manifest's bound stores** through Vector Stores Search, records bounded evidence passages and presents source links. The original knowledge files are not copied into the sandbox. The same OpenAI project must authorize the stores. Inventory checks support up to 1,000 files per bound collection. Retrieved sources are evidence, not proof that every answer claim is grounded; review citation fidelity in evaluations.

Application functions must be explicitly registered with **both** `read_only=True` and `replay_safe=True`. Imported descriptions and Action schemas grant no execution rights. The dependency-free schema validator accepts a conservative JSON Schema subset and rejects unsupported keywords. Results are committed before delivery, so recovery can reuse them. An execute-before-commit crash can replay a read; adapters must be safe under that condition. Tool calls are limited (12/run default), arguments/results are bounded, and local handler waiting times out after 30 seconds. Python cannot forcibly stop a handler thread; adapters need their own transport timeouts and must never perform writes.

Chat input limits remain **5 files, 10 MiB/file, 20 MiB/message and conversation**. Agents stages originals in `/workspace/inputs/<run-id>/`; small initial inputs are inline, larger/follow-up inputs use owned Files API resources with `purpose=user_data`. Attachments are distinct from permanent knowledge. The sandbox has no Studio API credentials or network access. Runtime package preparation uses pinned PDF/Office/spreadsheet libraries. Files and tool results remain untrusted content.

OpenAI publishes hosted files under `/workspace/outputs` as turn artifacts ([files and artifacts](https://developers.openai.com/api/docs/guides/agents-api/environments/files)). Studio accepts only artifacts belonging to the expected session and completed turn, normalized safe paths, allowed extensions and verified lengths: **25 MiB/file and 100 MiB/run**. Accepted types are TXT, MD, JSON, CSV, TSV, PDF, DOCX, XLSX, PPTX, PNG, JPEG and WebP. HTML, SVG, archives and executable code are excluded. Downloads use app-scoped IDs, `application/octet-stream`, `nosniff` and attachment disposition. They are not rendered as executable previews. Provider completion with invalid files fails local finalization; it is not shown as a complete deliverable.

## Storage and cleanup

Local `managed.sqlite3` stores private prompts, attachment bytes and run payloads; `managed-artifacts/` stores binary outputs. Browser recovery storage contains IDs only. These files are excluded from exports and Git. Local data is not encrypted at rest. Agents sessions and sandbox content also live with OpenAI; Responses `store:false` does not apply to managed session persistence.

**Archive & delete runtime files** deletes only owned sessions/runtime uploads and local artifact bytes; the local text transcript remains archived. Shared knowledge/vector stores are retained. Default expiry is seven days after the latest run activity; cleanup runs at server startup and periodically while running. Failed remote deletion stays pending and is retried. Provider acknowledgement is recorded; it is not a promise of physical erasure or deletion from provider backups. Unknown submissions without IDs require operator reconciliation. A crash between remote resource creation and saving its ID can require manual orphan cleanup.

## Standalone applications

```sh
python3 -m gptapps check workshop.json
python3 -m gptapps build workshop.json --out dist/research-workshop
cd dist/research-workshop
./start.sh --port 9000
# Or:
./docker-start.sh --port 9000
```

Open http://127.0.0.1:9000. Agents exports install the pinned SDK automatically in a local virtual environment or their Python 3.13 Docker image; Responses exports need no third-party Python packages. Both have the same task/attachment UI and bottom-left version/build. No generator process is needed. For manual Agents startup install `requirements.txt` in a virtual environment before `python run.py`. Keep `app.json` and private history out of public repositories. Existing downloads need a fresh export; changing the framework does not update them.

## Evaluate before production

Deterministic protocol tests establish lifecycle behavior, not task quality. Version, model, instruction, tool, knowledge and policy changes need representative comparisons, including document attacks, uncertain sources, long tasks, refusal, artifacts and recovery. Start with `examples/workshop-evaluation.example.json`, customize its prompts/rubrics and agree pass-rate/latency thresholds with your app owner. Its thresholds are examples, not measured quality targets.

```sh
# Prepare only: no provider calls. Use a fresh output filename.
python3 -m gptapps evaluate workshop.json \
  --suite examples/workshop-evaluation.example.json \
  --out .gptapps-data/evaluations/draft.json

# Explicit paid run: each case executes Responses baseline and selected candidate.
python3 -m gptapps evaluate workshop.json \
  --suite examples/workshop-evaluation.example.json --execute \
  --out .gptapps-data/evaluations/comparison.json

# After a human fills each row's review, reviewer, notes and every rubric check:
python3 -m gptapps check workshop.json \
  --release-report .gptapps-data/evaluations/comparison.json
```

The baseline uses the same instructions/bindings/model with the Responses runtime. Unsupported baseline tools must be adapted and compared deliberately; a failed baseline is a hold. Each case starts a new conversation. Attachments can be supplied in the suite as the same explicit `{name,data}` base64 objects as chat; these fixtures and reports can contain sensitive material and belong in private storage. Trusted custom handlers use `--extension module:setup` on `evaluate` as on `serve`.

Reports record final answers, public receipts, usage, latency, app fingerprint and source-code revision. They exclude hidden reasoning. Human review must assess task completion, answer correctness, instruction following, grounding and the content of every expected artifact. Edit each row, for example:

```json
"review": {
  "reviewer": "App owner",
  "notes": "Compared both answers and opened the output file.",
  "checks": {"Correct and follows instructions": true, "Artifacts are usable": true}
}
```

Check names must exactly match the case rubric. Unexecuted/unreviewed cases, technical failures, stale configuration/code and failed critical cases hold release. The CLI exits `2` for a hold. Studio shows the report saved at `<data>/evaluations/<app-id>.json`; copy a reviewed comparison there and refresh. Validate extension code and externally edited knowledge separately: the code digest covers packaged Python modules, not outside adapters or mutable provider data. This is an owner-controlled review record, not an independent certification or signed attestation.

Development chat and ZIP downloads remain available under **Experimental · release hold**. A ZIP contains `release-status.json` with that hold. There is no production deployment button in this local prototype; deployment pipelines should require the release check. Behavioral release approval remains pending until real project access, representative runs and human review are supplied. Provider tracing helps investigation; it does not replace evaluation, authentication, application telemetry or production support.

## HTTP additions

All routes retain local host/origin checks and app scoping. They do not add multi-user authentication.

| Method / route | Purpose |
| --- | --- |
| `POST /api/runtime/check` | Builder-only deterministic compatibility check; no inference or live-access verification |
| `POST /api/runs` | Accept managed work with `app_id`, `message`, optional `session_id`/`attachments`, required `submission_id` |
| `GET /api/runs?app=...&submission_id=...` | Recover a lost acceptance response without resubmission |
| `GET /api/runs/{id}?app=...` | Read a scoped run snapshot |
| `GET /api/runs/{id}/events?app=...&after=0` | Replay durable public events, then observe new events |
| `POST /api/runs/{id}/cancel` | Request cancellation with `app_id` |
| `POST /api/runs/{id}/reconcile` | Recheck a known provider session with `app_id` |
| `GET /api/artifacts/{id}/content?app=...` | Download a validated output file |
| `GET /api/sources?app=...&run=...&source=...` | Read a bounded retrieved knowledge passage |
| `POST /api/sessions/cleanup` | Explicit `{app_id,session_id,confirm:true}` owned-resource cleanup |

## Still deferred

Agents Auto routing, runtime switching, multi-agent delegation, write integrations, arbitrary MCP, self-hosted sandboxes, schedules, browser/computer use and an agent that writes tailored frontend source. Private-repository SSO and the experience designer are not included in this public branch. Neither runtime guarantees Custom GPT behavior parity.
