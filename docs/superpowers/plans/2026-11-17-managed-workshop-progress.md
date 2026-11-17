# Managed Workshop progress — plan: 2026-11-17-managed-workshop.md

Base: 345ee496308563748ec1e77ac7bc325cfc64cdcf. Branch: feat/managed-workshop.
Credential choice: owner authorized existing local key; no key available in current environment. Offline implementation proceeds; live access is not assumed.
Baseline: Python 3.14 unittest 160 tests OK (4 skipped). Initial sandbox-only failures were local socket restrictions; rerun with socket permission passed.
Ruling: reuse the clean public checkout on the explicitly requested new branch; no additional worktree or main changes.
Ruling: the user approved the reviewed design and asked for implementation, so execute the concrete plan without a second approval round.
Ruling: retain the dependency-free default; the official SDK is an optional Agents-only dependency.
Pre-flight: configuration produces validated runtime settings for the run service; run service produces scoped snapshots/events for HTTP and UI; export must bundle every new module and optional dependency metadata.

Task 1: in progress.

Task 1: complete — 11 configuration/provider-contract tests pass; corrected the fake SDK recorder signature after verifying the official positional session-ID contract.
Task 2: complete — 7 durable-run/artifact/tool-ledger tests pass.
Ruling: SDK 3.13 lacks a typed review keyword although the public API documents it; use the SDK-supported extra_body={review:auto_review} parameter explicitly.
Task 3: in progress.

Task 3: complete — 18 managed lifecycle tests plus facade integration pass. Includes confirmed cancellation, browser disconnect, restart, ambiguous submission, app-scoped knowledge, validated artifacts, replay-safe tools, single-supervisor locking, deadlines and cleanup retries.
Task 4: in progress.

Task 4: complete — runtime choice/model/environment controls, managed HTTP endpoints, saved execution UI and downloads verified with synthetic Studio and standalone browser flows. Reload reattached to an active task; final result/history/download verified. Mobile sidebar regression reproduced visually and corrected; no browser console errors.
Task 5: in progress — portable optional dependencies, local/Docker launchers, evaluation runner/gate, README architecture/API/release updates and version 0.3.0 implemented. Python 3.14: 219 tests OK with real Docker and optional SDK launcher checks. Python 3.11: 219 tests OK (6 opt-in tests skipped). Node: 30/30 pass. Official SDK 3.13 namespace and create/events/artifact/environment-file signatures verified without API calls.
Ruling: development chat and exports remain available under an explicit release hold; the check --release-report command gates production promotion — this prototype has no production deployment action, and representative model-quality thresholds still require owner review. Cost if wrong: an operator could bypass the documented gate in an external deployment pipeline.
Live verification: existing-key preference honored; no configured key/path is available, so no real OpenAI access or semantic-quality claim is made.
