# Managed Workshop progress — plan: 2026-11-17-managed-workshop.md

Base: 345ee496308563748ec1e77ac7bc325cfc64cdcf. Branch: feat/managed-workshop.
Credential choice: owner authorized existing local key; no key available in current environment. Offline implementation proceeds; live access is not assumed.
Baseline: Python 3.14 unittest 160 tests OK (4 skipped). Initial sandbox-only failures were local socket restrictions; rerun with socket permission passed.
Ruling: reuse the clean public checkout on the explicitly requested new branch; no additional worktree or main changes.
Ruling: the user approved the reviewed design and asked for implementation, so execute the concrete plan without a second approval round.
Ruling: retain the dependency-free default; the official SDK is an optional Agents-only dependency.
Pre-flight: configuration produces validated runtime settings for the run service; run service produces scoped snapshots/events for HTTP and UI; export must bundle every new module and optional dependency metadata.

Task 1: in progress.
