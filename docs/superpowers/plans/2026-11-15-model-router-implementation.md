# Cost-first model router implementation plan

> For agentic workers: implement inline with independent policy/client and UI subtasks; root integrates runtime/config/export and reviews the whole change.

Goal: approved cost-first routing in public Studio/application chat and generated apps, preserving fixed-mode behavior and exposing model/status reasons.
Spec: ../specs/2026-11-15-cost-first-model-router-design.md (approved by user2026-11-15).
Stack: Python3.11+ standard library, vanilla JS, existing SSE/SQLite, Decisions and Responses APIs.

## Constraints and review focus

Keep dependencies empty, all file intake limits, origin protection, fixed fingerprints, tool validation and save atomicity. No raw evidence logs, paid extraction, secret export, automatic answer retries or private-repo changes. Review untrusted policy/model outputs, unknown document context, mid-conversation model switches, router failures/cancellation, and standalone completeness.

## Task1 — policy, evidence and Decisions client (independent)

Own gptapps/routing.py, gptapps/decisions.py and focused tests. Validate policy and extract bounded evidence. ModelRouter(client=None).select(app,message,history,files,tools) returns routing record including requested_model, route, task, summary, reason_codes, fallback, router_model, policy_version, evidence, router_usage, selection_ms. No answer call here.

Policy schema: mode=cost_first, version, router_model=gpt-6-luna, timeout_seconds(default2), min_probability(default0.65), document_context_floor(default32768), fallback_model, candidates. Candidate: model, tier(economy/balanced/advanced), cost_rank(nonnegative integer), context_window, max_output_tokens, capabilities(text/documents/images/web_search/image_generation/code_interpreter/file_search/function_calling/structured_output). Fixed snapshot models only. Functions validate_policy(value), load_policy_file(path=None using OPENAI_ROUTING_POLICY_FILE) return canonical policy; no app/spec import. Unknown/bad config fails. Fallback balanced/advanced with document/image/text support. DecisionsClient.create(payload,timeout=...) uses hardcoded endpoint; DecisionsUnavailable for timeout/connection/5xx, fatal ValueError for auth/quota/refusal. Single request two typed questions named effort/task. Validate selected option probability; use fallback on uncertain/<0.65/invalid, pin model after select. Router excludes incompatible candidates; return sole eligible without API call. Preserve configured fallback eligibility before any Decisions request. Evidence budget exactly matches spec. No excerpts in returned routing record.

- [x] Write and observe failing tests for schema, bounds, capability filtering, typed answers, fallbacks, transport and malicious/metadata-only file evidence.
- [x] Implement and pass focused tests; report interface/results.

## Task2 — UI/status (independent)

Own gptapps/routing.js, routing.css, chat.html, chat.js and tests/test_routing_ui.js. Add accessible compact Routing status section and safe expandable details, fixed/Auto creation selection in model step, and current/saved/failed turn status. SSE event type routing has routing object; completed assistant message contains routing. Requested vs provider-reported model identity displayed accurately. Fixed UI supports the same metadata.

Root exposes config.routing_available boolean and optional routing_error safe string. Model step auto sends string auto through existing intake. Root embeds validated policy and keeps runtime.model null. UI must not persist raw excerpts, use unsafe HTML, claim prices/quality guarantees, or clear attachments on routing errors. Clear old status when starting/loading/changing app; restore latest saved routing record. Distinguish router model from answering model. Keep bottom-left version/build.

- [x] Write failing DOM/unit checks, implement safe rendering and lifecycle, run all dependency-free JS tests.

## Task3 — runtime/config/export integration (root)

Own runtime.py/spec.py/setup.py/web.py/build.py/templates/launchers/README/version. Runtime accepts optional decisions_client for tests; select after history load with original files, before Responses. Fixed configuration unchanged; Auto fingerprints app/policy rather than selected model. Emit routing before answer/after completion with requested/reported model, answer usage/timing; persist assistant.routing on successful turns only. Send full answering evidence unchanged and pin model per tool-round chain. Use stream callback before/after routing as disconnection checkpoints. Do not swallow callback failures as router fallbacks.

Auto builder/import: optional runtime.routing validated; model auto selects server policy snapshot via OPENAI_ROUTING_POLICY_FILE. Setup model step recognizes auto verbatim without a classification call; other setup behavior unchanged. Missing policy returns actionable error. Export snapshot and new source/assets; allow bounded public policy JSON example in Docker context. Add --routing-policy option and securely forward file config through local/Docker launchers with no credentials in image. Existing app.json snapshots need no external policy at runtime.

- [x] Failing integration tests for fixed compatibility, Auto creation/import, tool-round pinning, model switches/history, failure atomicity, original attachments and SSE history metadata.
- [x] Implement, run full Python/JS suites including Docker; maintain compatibility with prior apps.

## Task4 — documentation and release

Update README release rationale, pricing caveat, policy schema/setup, supported inputs and limitations; update both framework/generated-app architecture diagrams. Include accurate generated README. Bump public release0.2.0 because opt-in routing extends settings/API behavior. Update design status to approved; record verification and review.

- [x] Independent code review and resolve important findings.
- [x] Offline browser framework and fresh exported app, mobile status; wheel/Docker allowlists and metadata verification.
Release procedure: scan staged content, then commit/push public origin main after verification; report deployment/upgrade and opt-in configuration truthfully.

## Verification record

- Full Python suite with Docker enabled: 141 passed. Dependency-free Node suite: 24 passed. Wheel 0.2.0 built successfully.
- Independent final code review: no important findings.
- Offline Studio and exported-app browser checks: economy/advanced routing, safe timeout fallback, saved status, original document metadata, new conversations and responsive sidebar. User requested status below Recent Conversations; implemented in the shared template and both README diagrams.
- No live OpenAI calls, real-document uploads or savings/quality evaluation. Example candidate ranks and access remain operator-reviewed settings.
- Fixed a macOS Bash 3.2 no-policy launcher failure uncovered by Docker tests. Kept existing early-stream and atomic-save guarantees.
- Private repository unchanged.
