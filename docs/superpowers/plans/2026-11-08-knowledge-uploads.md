# Knowledge Uploads Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Upload multiple knowledge files from the framework UI to OpenAI, index them, and bind a ready collection to generated apps.

**Architecture:** A dedicated knowledge module owns provider requests and persisted upload metadata. Builder-only HTTP routes accept bounded raw file requests and expose upload/indexing status. The shared UI provides the setup-step picker and existing-app management; generated apps retain only retrieval.

**Tech Stack:** Python 3.11+ standard library, existing HTTP server, vanilla JavaScript/CSS, Files API, Vector Stores API, Responses file_search.

**Spec:** ../specs/2026-11-08-knowledge-uploads-design.md

## Global Constraints

- No third-party Python dependencies, plaintext keys in the browser, source-file persistence, live API tests, or automatic deletion of remote resources.
- Maximum 100 files, 25 MiB each, 100 MiB total; use the documented file-search formats.
- Existing app bindings change only after all new files index successfully. Uploads are builder-only.

## Review Focus

- Partial indexing failures must not produce a usable binding.
- A browser reload must preserve uploaded provider IDs and support status recovery without duplicate upload.
- Unknown or mismatched upload/file IDs and cross-origin requests must fail before provider mutation.
- Binding must preserve app instructions, model, tools, and Actions while updating only knowledge.
- Generated ZIPs must carry the ready vector store binding and no uploaded source bytes, secrets, or upload-state files.

### Task 1: Provider and persistent upload manager

**Files:** create `gptapps/knowledge.py`, `tests/test_knowledge.py`.

**Interfaces:** `KnowledgeClient.create_store`, `upload_file`, `create_batch`, `get_batch`; `KnowledgeManager.start(files)`, `upload(id,index,data)`, `index(id)`, `get(id,refresh=False)`, `list()`, `apply(id,app)`, `claim(id,app_id)`.

- [x] Write failing provider-boundary and manager tests: actual multipart/auth requests, validated multiple-file lifecycle, restart/resume, duplicate mutation protection, failed counts, safe errors, ready-only binding and unchanged app fields.
- [x] Run `env PYTHONPATH=tests python3 -m unittest test_knowledge -v` and inspect the failures.
- [x] Implement the module with atomic private JSON metadata, no persisted file bytes, validated provider IDs, and sanitized errors.
- [x] Run the tests to green.

### Task 2: Builder routes and app binding

**Files:** modify `gptapps/web.py`, `tests/serve_fixture.py`; create `tests/test_knowledge_http.py`.

**Interfaces:** JSON POST `/api/knowledge` starts a collection; raw POST `/api/knowledge/file?id=…&index=…` uploads a slot; JSON POST `/api/knowledge/index`; GET `/api/knowledge` lists records; GET `/api/knowledge/status?id=…` refreshes indexing; JSON POST `/api/knowledge/bind` binds an existing app; app creation accepts `knowledge_upload_id`.

- [x] Add failing HTTP tests for ready creation, blocked pending/failed binds, standalone denial, origin/size checks, and generated ZIP contents.
- [x] Implement builder-only routes with bounded body reads and app writes under the runtime lock; use atomic manifest replacement for existing apps.
- [x] Verify the HTTP tests and existing suites.

### Task 3: UI, documentation, and verification

**Files:** modify shared chat HTML/JS/CSS, setup copy, README, generated README, and optional browser smoke coverage.

- [x] Demonstrate the missing uploader in the browser before implementing it.
- [x] Add the setup and existing-app panel: multiple picker, selected file list, recent collection picker, sequential uploads, progress polling, explicit ready binding, and clear failure/recovery feedback.
- [x] Preserve no-knowledge setup, navigation guards, chat state, and standalone behavior.
- [x] Exercise the complete flow with synthetic files in the browser; inspect a saved screenshot.
- [x] Update documented API calls, limits, retention, run/deployment behavior, and generated-app instructions.
- [x] Run `env GPTAPPS_TEST_DOCKER=1 python3 -m unittest discover -s tests -v`, `node --test tests/test_chat_stream.js`, and JS syntax validation; review the final code and verify any fixes.

## Execution notes

The user authorized this implementation. Continue in the current shared checkout; it is not a Git repository, so worktree/commit operations are inapplicable. Routine implementation choices are recorded in the design rather than introducing a new approval gate. Track verified steps below.


## Verified completion

- Task 1 complete: provider/manager regressions observed RED then GREEN. Multipart bytes, Unicode names, limits, recovery, indexing failures, and ready-only binding covered.
- Task 2 complete: HTTP regressions observed RED then GREEN. Existing/new app bindings, standalone denial, origin and body limits, on-disk edit protection, and ZIP contents covered.
- Task 3 complete: real in-app browser selected two files, uploaded/indexed them with a simulated provider, attached to an existing app, reused the collection during new-app setup, created a runtime-ready app, and checked no-file/clarification paths. Desktop/mobile screenshots were saved and inspected; no horizontal mobile overflow and 44px action targets were observed. Browser error log was empty.
- Full suite: 89 Python tests passed, including actual Docker builds/launches; 6 Node tests passed; both JS files passed syntax checks.
- Root README and generated README now include framework ingestion and generated-app retrieval architectures, enumerated APIs, setup/use instructions, limits, recovery, project access, and retention.

## Independent review and decisions

A fresh read-only reviewer inspected the complete implementation. No critical issues were found. The identified issues were addressed with regressions:

- Authenticated knowledge requests now reject redirects; a synthetic 302 proves no second request occurs.
- Repeated upload clicks on the same indexing collection are disabled and independently guarded. The Node regression observed duplicate mutations before the fix and zero afterward.
- Runtime packaging uses known files/assets only. A regression with private upload state and chat data nested under the source package proves they are excluded.
- Ready attachment accepts a valid manifest without the optional requirements mapping.
- Decision: keep per-file provider IDs/sizes only in local upload records; the exported manifest needs the vector store ID and filenames. ZIP and browser-created manifest checks confirm this.
- Decision: retain uploads in OpenAI until the owner manages them there; do not delete remote resources automatically. The UI and documentation explain retention and possible storage/usage charges.
- Review limits: no live OpenAI upload/retrieval/billing test was performed; tests use synthetic files and a simulated provider. Shared multi-process data coordination remains outside this documented single-user starter.

No deferred minor findings remain. The current folder is not a Git repository, so no branch or commit was created.
