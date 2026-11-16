# Prompt-specific Routing Explanations Implementation Plan

> **For agentic workers:** execute inline using superpowers:executing-plans and test-driven-development.

**Goal:** Explain each normally classified Auto request in plain, prompt-specific language, show the actual policy/model-selection rule, document cost/limits, test and push the public release.

**Architecture:** Decisions continues to select effort/task categories. After selection and a disconnect checkpoint, one separate tool-free Responses request to the router model creates a short public request assessment from the same bounded evidence. The assessment cannot alter model selection. Local policy facts, skipped-classifier and fallback reasons remain server-authored. Failed explanations keep those facts and do not prevent the first answer attempt. Fixed and sole-candidate/fallback routes need no explanation request. No extra call on history load or tool rounds.

**Approaches:** Decisions only supports typed categories/scores, so adding a free-text answer to it is unsupported. Replacing Decisions would change the approved router. A bounded Responses assessment preserves selection behavior and adds the requested prompt-specific explanation; it adds input/output usage and latency, which must be visible separately. Answer generation and app instructions stay unchanged.

**Spec:** User request in this chat on 2026-11-15: clear prompt-specific selection explanation, README, tests, commit/push. Implementation choices: 3-second explanation transport timeout, 512 output-token cap, 120-character request summary plus 180-character effort reason, no tools/retries/provider redirects, store:false, 64-KiB reply limit. Use existing API-key configuration; no live OpenAI calls during verification.

**Tech stack:** Python 3.11+ standard library, vanilla JS/SSE/SQLite and existing explicit standalone allowlists.

## Constraints and review focus

Keep fixed fingerprints, original inputs, pinning, attachment limits and atomic history save. No raw evidence logs or binary-file extraction; compact derived assessments are saved with the turn. Treat evidence as untrusted input, label generated assessments, and never present them as internal reasoning or a quality guarantee. Validate output and model IDs, preserve known metadata-only/truncated evidence limits, and keep the authoritative policy reason visible on failures. Existing saved records without assessments remain readable. Private repo untouched.

## Task 1 — selection facts and bounded assessment

- [x] Add failing runtime/core tests for prompt-specific saved assessment, actual selection rule, separate usage, evidence limits, cancellation and preserved answering inputs.
- [x] Add `gptapps/explanations.py` with bounded no-redirect client and strict assessment parser; no returned model/policy override is consumed.
- [x] Add classified effort/selection rule facts to `routing.py`; integrate one explanation between disconnect checkpoints in `runtime.py` with injectable external client.
- [x] Pass unit/HTTP tests for valid, timeout, refusal, malformed/oversized, injection-like and metadata-only evidence, fixed/skipped/fallback behavior and no retry.

## Task 2 — shared UI, exports and docs

- [x] Add failing JS checks for visible assessment, real applied policy rule, unavailable/legacy state, safe text and usage; implement shared sidebar rendering.
- [x] Add module to standalone allowlist, update generated README, main README release notes/cost/API/privacy/diagrams, and bump VERSION to 0.2.2.
- [x] Run full Python/Node suites with Docker, wheel/export/syntax/privacy checks; browser-verify Studio and a fresh standalone export with offline providers.

Release procedure: review the final diff and evidence, scan staged content, commit and push public origin main after checks pass.

## Verification — 2026-11-15

- Initial regressions failed on missing persisted assessment and generic UI text. Focused explanation/core/runtime/UI checks pass after implementation.
- Final full suite: 160 Python tests with Docker enabled; 26 dependency-free Node tests. Python 3.11 and 3.14 both pass all 37 focused routing/explanation checks.
- Independent review identified parser-recursion failure handling on Python 3.11 and inaccurate absent-tier wording. Both were reproduced with regressions, fixed and re-reviewed; no remaining important finding.
- Offline browser verification covers Studio and a fresh standalone export: specific Spanish-greetings assessment, different advanced planning assessment/model, saved-history restoration, separate explanation usage/rule detail, and visible explanation-timeout recovery while the answer succeeds. Narrow-screen controls expose the routing panel; temporary viewport changes were reset.
- No live OpenAI calls, real documents, new credentials or private-repository modifications. The optional assessment adds one bounded request on normal classifications, with no retry and no second answering-model attempt.
