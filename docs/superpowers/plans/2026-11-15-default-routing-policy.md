# Default Routing Policy Implementation Plan

> **For agentic workers:** implement inline using superpowers:executing-plans and test-driven-development.

**Goal:** `start.sh` and `docker-start.sh` offer Auto using the bundled `routing-policy.json` without a flag; `--routing-policy FILE` selects another policy.

**Architecture:** The shared framework launcher resolves explicit flag > existing `OPENAI_ROUTING_POLICY_FILE` environment setting > repository-root starter file. Existing validation/export and Docker read-only mounting apply to the resolved path. Generated launchers continue to use their embedded application policy.

**Tech Stack:** Bash 3.2+, Python 3.11+ standard library, existing Docker/HTTP integration tests.

**Spec:** User instructions in this chat on 2026-11-15: default the policy in both framework launchers, preserve the file override, and document it.

## Global Constraints

No runtime dependency, credential, live OpenAI call, private-repository change, or automatic switch of saved fixed-mode applications. Bump release to 0.2.1 and preserve the version/build footer. Use existing checkout and execute inline as authorized.

## Review Focus

- Default resolves from framework root, even when called from another working directory.
- Explicit flag wins over inherited environment; environment overrides remain supported.
- Docker receives the resolved file by read-only mount, rather than a host-only environment path.
- Missing/unreadable overrides fail before server startup, with no silent fallback.
- Generated fixed/Auto exports remain self-contained and do not depend on the starter file.

## Task 1: default resolution and documentation

- [x] Add real local/Docker launcher tests that create an Auto app without a flag and inspect its saved policy; add explicit/environment override and unreadable override checks.
- [x] Observe the default tests fail because Auto is unavailable.
- [x] Default the framework helper to repository-root `routing-policy.json`; retain explicit/env precedence and validation; explain default in launcher help.
- [x] Update README launch examples, routing setup, configuration table, troubleshooting, release notes and framework diagram. Set VERSION to 0.2.1.
- [x] Run full Python/JavaScript suites with Docker, syntax/diff/privacy checks, and inspect version/policy export behavior.

Release procedure: stage only the public starter policy, launcher, documentation, version and relevant tests; commit and push after verification.

## Verification — 2026-11-15

The red run failed specifically for no-flag local and Docker startup (`routing_available` was false); environment/explicit override and unreadable-file cases already passed. After the shared default was added, all six router HTTP/launcher tests passed. The full suite passes: 144 Python tests with Docker enabled and 24 Node tests. Bash syntax checks and wheel build 0.2.1 pass. Docker verifies creation and snapshot of an Auto app using the bundled file without a flag; existing explicit-override and generated fixed/Auto launcher checks pass. Verification uses synthetic configuration, temporary data and placeholder credentials, with no OpenAI requests.

Final review confirms explicit flag > nonempty environment > repository-root file, absolute host-path resolution before Docker mounting, read-only policy mounting, no generated-launcher dependency on the starter, and no credentials in policy or packaging.
