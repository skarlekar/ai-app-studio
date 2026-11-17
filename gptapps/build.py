"""Package a standalone app without credentials, runtime data or dependencies."""
from pathlib import Path
import json
import shutil

from .spec import analyze, validate
from .version import stamp_build


def copy_runtime(destination):
    """Export known source/assets only, even when --data lives beneath this package."""
    package = Path(__file__).parent
    files = ["__init__.py", "version.py", "__main__.py", "build.py", "cli.py", "extensions.py", "runtime.py", "setup.py",
             "spec.py", "web.py", "attachments.py", "attachments.js", "routing.py", "decisions.py", "explanations.py", "routing.js", "routing.css", "knowledge.py", "chat.html", "chat.js", "knowledge.js", "chat.css", "LICENSE",
             "agents_config.py", "agents_client.py", "agents_runtime.py", "runs.py", "tools.py", "evaluation.py", "workshop.js", "workshop.css"]
    files += ["templates/" + name for name in ("start.sh", "docker-start.sh", "launcher-common.sh", "docker-entrypoint.sh", "Dockerfile", ".dockerignore")]
    files += ["vendor/" + name for name in ("marked.umd.js", "purify.min.js", "marked-LICENSE.txt", "dompurify-LICENSE.txt", "README.md")]
    files += ["icons/" + name for name in ("plus.svg", "download.svg", "history.svg", "arrow-up.svg", "arrow-up-right.svg", "chevron-down.svg", "lock-keyhole.svg", "layers.svg", "LICENSE.txt", "README.md")]
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package / name, target)


def build_app(app, destination):
    validate(app)
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    copy_runtime(root / "gptapps")
    stamp_build(root / "gptapps")
    shutil.copyfile(Path(__file__).with_name("LICENSE"), root / "LICENSE")
    templates = Path(__file__).with_name("templates")
    for source, destination in (
        ("start.sh", "start.sh"), ("docker-start.sh", "docker-start.sh"),
        ("Dockerfile", "Dockerfile"), (".dockerignore", ".dockerignore"),
        ("launcher-common.sh", "scripts/launcher-common.sh"),
        ("docker-entrypoint.sh", "scripts/docker-entrypoint.sh"),
    ):
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(templates / source, target)
        if target.suffix == ".sh":
            target.chmod(0o755)
    for name, data in (("app.json", app), ("compatibility.json", analyze(app))):
        (root / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    (root / "run.py").write_text(
        'from pathlib import Path\nfrom gptapps.web import serve\n\n'
        'root = Path(__file__).resolve().parent\n'
        'serve(root / "app.json", root / ".gptapps-data")\n')
    (root / "README.md").write_text(standalone_readme(app))
    from .agents_config import SDK_REQUIREMENT
    (root / "requirements.txt").write_text(SDK_REQUIREMENT + "\n" if app['runtime']['api'] == 'agents' else '')
    (root / "requirements-agents.txt").write_text(SDK_REQUIREMENT + "\n")
    (root / 'release-status.json').write_text(json.dumps({'status':'release_hold','reason':'Export is available for experimentation. Run task-specific evaluations and complete human review before production.'},indent=2)+'\n')
    (root / ".gitignore").write_text(
        ".gptapps-data/\n.env\n.env.*\n!.env.example\n*.pem\n*.key\n"
        "__pycache__/\n*.py[cod]\n.venv/\n.venv-agents/\n*.sqlite3\n*.sqlite3-*\n*.log\n.DS_Store\n"
        "# Private GPT configuration; deliberately review before publishing.\napp.json\ncompatibility.json\n")


def standalone_readme(app):
    runtime = app['runtime']['api']
    intro = f"**Runtime:** {runtime}. **Release readiness:** experimental; evaluation required before production.\n\n"
    if runtime == 'agents':
        intro += ("This app uses OpenAI Agents API managed sessions with an explicit fixed model. "
                  "`./start.sh` installs openai==3.13.0 in `.venv-agents`; `./docker-start.sh` includes it in the Python 3.13 image. "
                  "For manual startup, create a virtual environment and install `requirements.txt` first. "
                  "Use a server-side application key with Agents read/write and Responses write access and the configured model/tool permissions.\n\n"
                  "The task timeline and managed execution panel show progress, receipts, cancellation and safe artifact downloads. "
                  "A browser disconnect does not cancel work; reload or open its saved conversation to reattach. "
                  "Keep the server running for supervision and cleanup. Unknown submissions are not silently resent. "
                  "Check OpenAI project logs before resubmitting an unresolved task.\n\n"
                  "Chat inputs are staged in the hosted workspace, not sent as Responses inline inputs. "
                  "Sandbox network access is disabled; no server keys enter the workspace. "
                  "App-bound knowledge is retrieved through Vector Stores Search and replay-safe read tools. "
                  "Artifacts are limited to 25 MiB/file and 100 MiB/run, validated for ownership/path/type/length, and download-only. "
                  "Seven inactive days of retention apply by default while the server runs. Explicit cleanup archives local text history, "
                  "removes owned runtime resources, retains shared knowledge, and retries unconfirmed provider deletion.\n\n")
    return f"# {app['name']}\n\n" + intro + """A standalone chat application generated by GPT Application Framework. It includes
its own backend, web interface, configuration, and launchers. You do not need the
original framework folder or access to the original GPT in ChatGPT.

## Model routing and status (Responses runtime)

An Auto app embeds its approved routing policy in `app.json`. It calls OpenAI
Decisions API (`/v1/decisions`) to choose an eligible answering model, then uses
Responses API (`/v1/responses`) to generate and stream the answer. The **Routing status** panel in the left sidebar, below **Recent Conversations**,
shows the requested/provider-reported model, a prompt-specific request assessment,
the actual policy rule, fallback and separate classifier/explanation/answer usage. Saved turns
retain this information. On narrow screens, open **Conversations and routing** in
the header to view it. Fixed-model apps continue to use their configured model.

No external routing-policy file or `OPENAI_MODEL` default is required for an
exported Auto app. Set its usual `OPENAI_API_KEY` and ensure every configured
candidate and the router model are available to that OpenAI project. The launchers
read the embedded fallback model and do not prompt for an unused fixed default.
Changing the embedded policy requires restarting and beginning a new conversation.

Routing uses the request, recent history, file metadata and bounded readable text.
PDF/Office/image contents are not extracted for routing; the answering model still
receives the original files. Cost ranks are configured expectations, not live
prices or a promise of savings. See the policy and README in the framework for
capability/cost verification before real use. Timeout/invalid decisions can use
the configured compatible fallback; authentication, refusal and quota errors
remain visible. The app never automatically pays for another generated answer.

For a normal Auto classification, one extra tool-free Responses request to
`gpt-6-luna` generates a brief request assessment from the same bounded evidence.
It uses `store: false`, `reasoning.effort: none`, a 512-output-token cap and a
3-second transport timeout. This adds API usage and latency; it cannot change the
selected answer model. An unavailable/refused/invalid explanation retains the
policy reason and continues the first answer attempt without retrying the
explanation. Fixed, sole-candidate and fallback routes skip this call. Saved turns
retain the derived assessment; older history stays readable, and loading it or
running function-tool rounds does not generate another assessment. This is a
public assessment, not hidden reasoning or a quality guarantee. It can describe
private task context, so protect the local history directory.

## Chat attachments

Use **Attach files** beside the message box or drag files into the chat. Review
or remove selected files, type your question, then Send. File-only messages also
work. You can attach up to 5 files, 10 MiB per file and 20 MiB total per message
and conversation. Supported formats include PDF, Word, PowerPoint, Excel,
text/Markdown/JSON/CSV/code, and PNG/JPEG/WebP images. Your chosen model must
support the input types; PDF/image questions need vision support.

Responses apps send files with your text as inline file/image inputs. Agents apps stage originals in their hosted workspace; no-workspace mode cannot accept chat files.
They are not uploaded to a vector store or made permanent app knowledge. Chat
files are saved with local private conversation history and replayed on follow-up
turns, which can increase input-token costs. Session UI endpoints return metadata
only. Keep the local data directory private; history is not encrypted at rest.
Responses failures retain your draft and selected files for retry. Managed submissions use durable IDs: reconcile an accepted or unknown outcome before resending. A new conversation
clears unsent attachments. Existing generated apps need a fresh export to receive
this feature. The version and export build number appear at the bottom left.

## Chat rendering

The chat streams text as it is generated and safely renders Markdown headings,
bold/italic text, lists, links, tables, blockquotes, and code blocks. Saved
conversations use the same renderer. Browser libraries and their licenses are
bundled under `gptapps/vendor/`; no CDN is needed. Scripts, unsafe HTML/links, and
external Markdown images are excluded from model output.
Locally bundled Lucide icons and their license are under `gptapps/icons/`.

## Quick start: local Python

Extract the complete ZIP into its own folder. Open a terminal in that folder,
where `app.json` and `start.sh` are located, then run:

```sh
./start.sh
```

If executable permissions were lost during extraction, use `bash start.sh`.
The launcher checks for Python 3.11+, prompts securely for a missing API key and
default app model, starts the app, and opens http://127.0.0.1:8765 when ready.
The key stays in the process environment and is not saved to disk. Leave the
terminal open; press Ctrl+C to stop the app.

If `app.json` already specifies `runtime.model`, no default model prompt is needed.
Otherwise, an example API model ID is `gpt-6.1-sol`. Use a model available to your
project that supports this app's selected tools. API usage is billed to your
OpenAI API project. A ChatGPT subscription does not configure API access.

## Quick start: Docker

Install and start Docker Desktop or Docker Engine, then run from this folder:

```sh
./docker-start.sh
```

This builds an image containing Python 3.13, prompts for missing settings, waits
for readiness, and opens the browser. Host Python is not required. Press Ctrl+C
to stop and remove the container. `app.json` is mounted read-only at runtime;
private GPT instructions and keys are not copied into the image. History and
generated images stay in the host's `.gptapps-data/` folder across restarts.

## Examples and settings

```sh
# Either launcher accepts the same options.
./start.sh --port 9000
./docker-start.sh --port 9000 --no-browser
./start.sh --data ./my-chat-history
./start.sh --help
```

With port 9000, open http://127.0.0.1:9000. Relative data paths resolve from this
application's folder. The launchers reuse `OPENAI_API_KEY` and `OPENAI_MODEL` if
already exported. `runtime.model` in `app.json` takes precedence over the environment
default; edit it or set it to null if you want to use `OPENAI_MODEL` instead.
`OPENAI_SETUP_MODEL` is not needed for this generated app. No `.env` file is loaded
automatically. Never put the key in `app.json`, instructions, or browser chat.

## Run manually

From this folder, after setting the key and model in your terminal environment:

```sh
python3 -m gptapps check app.json
python3 run.py
```

Open http://127.0.0.1:8765 yourself. For a custom port without a launcher:

```sh
python3 -m gptapps serve --apps app.json --data .gptapps-data --port 9000
```

On Windows PowerShell, Python 3.11+ can run the application directly:

```powershell
$apiKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $apiKey).Password
$env:OPENAI_MODEL = "gpt-6.1-sol"
py -3 -m gptapps check app.json
py -3 run.py
```

The Bash launchers require Bash; the Python entrypoint works without Bash. Open
http://127.0.0.1:8765 after starting it. Responses requires no third-party Python packages. Agents requires the pinned `requirements.txt` installed in your chosen Python environment.

## Evaluation and release readiness

The export includes `release-status.json` with a release hold. Chat and downloads
are available for experimentation. Production decisions require representative
baseline/candidate evaluations, inspection of artifacts and human rubric review.
`python -m gptapps evaluate app.json --suite YOUR_SUITE.json --out .gptapps-data/report.json`
prepares a report without API calls; add `--execute` explicitly to run paid
Responses baseline and candidate requests. After review, use
`python -m gptapps check app.json --release-report .gptapps-data/report.json`.
Missing, stale, unexecuted or unreviewed reports hold release (exit 2).
See the framework's Managed Workshop guide for the suite and review format.
Reports contain private prompts/answers and must not be published unreviewed.

## Compatibility and troubleshooting

- Review `compatibility.json` or run the check command before relying on the app.
- Empty knowledge and Action lists are valid. The framework's Knowledge files
  panel can upload/index multiple documents and include the ready vector store
  binding in this app. Use an API key from the same OpenAI project with access to
  those files/stores. For an older unbound app, attach its collection in the
  framework and re-download it. Actual Actions need registered adapters.
- If the port is occupied by the framework or another app, use `--port 9000`.
- If Docker cannot connect, start Docker Desktop/the daemon and retry.
- Open the served HTTP URL; opening `gptapps/chat.html` directly cannot run chat.
- If an answer reaches its output-token limit, usable text is saved with a partial
  answer notice. Click Continue response to send a follow-up in the same conversation.
  Continuation is manual; the app does not retry or keep generating automatically.
- Review `runtime.max_output_tokens` in `app.json` for long answers. New app
  configurations default to 16,384; older configurations often retain 2,048 even
  after rebuilding. The limit includes reasoning as well as visible text. For
  example, set it to `16384`, restart, and start a new conversation. Larger budgets
  up to 131,072 are accepted by the framework, subject to your model's actual output
  and context limits; higher budgets permit greater API usage. No usable text,
  incomplete structured JSON, and incomplete function calls still produce an error
  instead of being saved or executed. The error identifies known length-limit causes.
- If a stream is interrupted, partial text is not saved as a completed turn. The
  input is restored for retry. If completion could not be confirmed, inspect saved
  conversations before resending. Restart the server and refresh the browser after
  updating runtime/UI files. Older app downloads need a new build to get these features.
- Changing the manifest or model requires restarting the server and starting a
  new conversation. The server does not reload edited configuration automatically.
- Missing/invalid API credentials, model access, billing, or unsupported tools
  must be resolved in your API project. Setup does not guarantee live API access.
- HTTP 429 can mean temporary rate limiting or an API billing/quota limit. The
  error identifies recognized codes. For `credit_balance_exhausted` or
  `insufficient_quota`, check API credits and limits for the key's organization/
  project; ChatGPT subscription billing is separate. For a spend/usage-limit code,
  address the applicable limit. Retrying does not restore credits or raise limits.
- For `rate_limit_exceeded`, `rate_limit_error`, or `slow_down`, follow the displayed
  wait time and reduce request frequency/concurrency before retrying. The client
  does not automatically retry requests. An unrecognized HTTP 429 remains ambiguous.

API account links: [billing](https://platform.openai.com/settings/organization/billing)
and [limits](https://platform.openai.com/settings/organization/limits). See OpenAI's
[error code guide](https://developers.openai.com/api/docs/guides/error-codes).

## Architecture and knowledge files

```mermaid
flowchart LR
    UI[Browser chat] <--> Server[Local Python server]
    Config[(app.json: instructions, model, vector store IDs)] --> Runtime[Chat runtime]
    Key[Server environment: OPENAI_API_KEY] --> Runtime
    Server <--> Runtime
    Runtime <--> History[(Local SQLite history)]
    Runtime <--> Responses[OpenAI Responses API]
    Responses -->|If knowledge is bound| Search[Hosted file_search]
    Search <--> Knowledge[(OpenAI vector store)]
    Search --> Responses
```

When you attach knowledge, the framework prepares it before packaging this app:

```mermaid
flowchart LR
    Documents[Owner selects multiple documents] --> Builder[Framework uploader]
    Builder --> Files[OpenAI Files API]
    Files --> Index[OpenAI Vector Stores file batch]
    Index --> Ready{All files indexed?}
    Ready -->|Ready| Binding[Vector store ID saved in app.json]
    Ready -->|Not ready| Wait[Progress or error; no binding]
```

This app reads that binding and uses Responses `file_search` to retrieve relevant
content and return answers with file citations. Your key stays on the server.
The framework does not need to be running alongside this app. Uploaded documents
and the vector store remain in their original OpenAI project; use a key that can
access that project. Copying this app to another computer does not transfer the
hosted store. Source documents, per-file upload metadata, and builder upload-state
records are excluded from the generated package. To change knowledge, return to
the framework, select/upload a ready collection, attach it, and re-download the app.

## Data, API use, and source license

App chat calls OpenAI's Responses API. Optional hosted tools run through that API.
Builder controls, app creation, and AI-assisted setup are disabled in this app.
Knowledge retrieval uses Responses `file_search` and the vector store IDs in
`app.json`. Uploading/indexing is performed in the framework builder through the
Files and Vector Stores APIs; this end-user app does not expose upload endpoints.
The original knowledge documents stay in your OpenAI project, separate from this
ZIP and local history. Storage/retrieval charges may apply. Cancelling setup or
deleting local app data does not delete those remote files or vector stores.
Messages persist in `.gptapps-data/sessions.sqlite3`; images are stored under
`.gptapps-data/assets/`. Stop the server before deleting that directory to clear
local history. Keep it to preserve conversations. Storage is local and unencrypted.

This is a local, single-user starter. Shared hosting needs authentication, user
isolation, budgets, HTTPS, and deployment controls. `app.json` contains your private
GPT instructions. Its contents and generated output are separate from the MIT
license covering the copied framework source in `LICENSE`. The included ignore
rules exclude private configuration, credentials, and runtime data from Git.
"""
