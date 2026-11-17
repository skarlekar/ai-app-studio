# Managed Workshop Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add an opt-in Agents API runtime to Studio and standalone exports while preserving Responses and its Decisions router.

**Architecture:** A shared runtime facade dispatches to existing Responses behavior or a managed-session supervisor. SQLite records submission IDs, provider sessions/turns, events, tool results and artifacts independently of browser connections. The optional official OpenAI Python SDK supplies typed Agents interfaces; default Responses installs remain dependency-free.

**Tech Stack:** Python 3.11+, sqlite3, vanilla JS, optional openai 3.13.0, unittest and Node built-in tests.

**Spec:** `docs/superpowers/specs/2026-11-17-managed-workshop-design.html` (approved design; original private review Site remains available).

## Global Constraints
- Work on `feat/managed-workshop` in the public repository; do not merge into main or modify the private repository.
- Preserve schema 1.0 Responses apps. Schema 2.0 explicitly supports `runtime.api=agents` or `responses`.
- Agents initially uses an explicit fixed model, one agent, `openai_hosted` (network disabled, automatic review) or capability-limited `none`.
- Existing chat intake limits remain 5 files, 10 MiB each, 20 MiB combined. Artifacts: 25 MiB/file, 100 MiB/run.
- Read-only external tools; validate arguments and app-owned store IDs. Local sandbox writes are permitted. No credentials in the sandbox or browser.
- One active managed turn/conversation, stable submission IDs, no resubmit after unknown outcomes; completion requires the intended turn status.
- Durable local run records and tool results, safe artifact downloads and cleanup inventory. No promise of exactly-once external execution.
- Export all runtime/UI modules, runtime-specific dependencies, local/Docker launchers and version/build footer. Update both README architecture diagrams.
- Full existing unittest and dependency-free Node tests plus new failure/recovery/HTTP/export tests before push. Live tests require locally configured existing key.

## Review Focus
- A browser retries an accepted task: preserve its run identity instead of executing twice (Task 2/3 tests).
- A tool completes just before a process dies: reuse committed output, replay only safe reads, reconcile unknown outcomes (Task 3 tests).
- A provider returns malformed/oversized/cross-turn files: reject and preserve explicit incomplete/failure state (Task 2/3 tests).
- A user switches app or changes manifest while work runs: reject cross-app access and pin the original configuration (Task 2/4 tests).
- A clean exported Agents app starts without the generator: dependency installation, SDK surface, version and local/Docker assets must be complete (Task 5 tests).

## Task 1: Configuration and provider contract
**Files:** spec.py, setup.py, agents_config.py, agents_client.py; tests/test_agents_config.py, tests/test_agents_client.py.
**Interfaces:** validate_agents_config(runtime)->dict; AgentsClient wraps the official sessions/files/vector-store interfaces and provides safe errors.
- [ ] Add failing tests for legacy compatibility, explicit Agents model, Auto rejection, unsupported capability blockers, SDK optional loading and safe SDK request construction.
- [ ] Run the tests and observe failure; implement versioned validation and deterministic runtime setup.
- [ ] Verify the tests pass; commit.

## Task 2: Durable run and artifact storage
**Files:** runs.py; tests/test_runs.py.
**Interfaces:** RunStore.create(app,session_id,submission_id,message,attachments)->run; get/list/events/update; tool-result ledger; artifact metadata/content; cleanup ownership.
- [ ] Add failing tests for duplicate submission/config changes/cross-app IDs, one active turn, monotonic events, binary privacy, path traversal/size limits and restart persistence.
- [ ] Implement transactional records and private bounded file storage; verify tests; commit.

## Task 3: Managed execution and recovery
**Files:** agents_runtime.py, runtime.py, tools.py; tests/test_agents_runtime.py.
**Interfaces:** ManagedRuntime.start/observe/cancel/recover/delete; Runtime facade preserves Responses API and exposes managed run service.
- [ ] Add failing fake-provider tests for streaming before terminal state, browser disconnect, follow-ups, call deduplication, ambiguous submission, tool crash window, cancel, expired environments, knowledge scoping, artifacts and retention.
- [ ] Implement supervised work, provider reconciliation, cancellation/deadline, knowledge bridge and owned-resource cleanup.
- [ ] Verify intended turn completion, source citations and safe error behavior; commit.

## Task 4: Product integration
**Files:** web.py, chat.html/js/css, workshop.js/css, routing.js; tests/test_agents_http.py, tests/test_workshop_ui.js.
**Interfaces:** existing /api/chat plus scoped /api/runs/{id}, /events, /cancel and /api/artifacts/{id}/content; submission IDs; runtime setup controls and task timeline.
- [ ] Add failing HTTP/client tests for runtime choice, app isolation, cancel/reconnect, download headers and legacy SSE compatibility.
- [ ] Implement runtime/model controls, capability preflight, run status/reattach and downloads; verify Studio and standalone behaviors.
- [ ] Capture and check UI; commit.

## Task 5: Portable builds, evaluation and documentation
**Files:** build.py, version.py, pyproject.toml, launchers, Docker templates, README.md, docs/managed-workshop.md, evaluation fixtures/runner; export and launcher tests.
**Interfaces:** standalone dependency metadata, `--agents` setup path, runtime-aware build allowlist, versioned evaluation report with no unearned release-quality claims.
- [ ] Add failing tests for optional SDK packaging, clean standalone start, Docker assets and evaluation release hold states.
- [ ] Implement packaging, launchers, documentation, architecture diagrams, release notes and evaluation tooling.
- [ ] Run full unittest/Node suites, offline end-to-end browser verification and bounded live check when configured.
- [ ] Request fresh whole-branch review; resolve important findings with reproducing tests; commit and push feature branch only.
