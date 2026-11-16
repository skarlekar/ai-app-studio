# Cost-first, attachment-aware model routing

Status: proposed design for user review. No router implementation is included.
Repository: public `skarlekar/ai-app-studio`; the private edition is outside this change.

## Intent and agreed requirements

Select an appropriate model for each application chat request to reduce overall API cost. The user accepts some answer-quality variation in exchange for greater savings. Requests can include attached documents. Routing uses the request, conversation context, file metadata and readily available text (approach1). The framework must show the model used and a short explanation in a status section. Generated standalone applications inherit the feature.

The decisions below that were not specified by the user are proposed defaults, not previously approved requirements.

## Approaches considered

1. **Lean evidence routing — selected:** evaluate request/context, attachment metadata and bounded text already readable locally. Low processing overhead; binary document complexity may be unknown.
2. **Extract every document before routing:** gives more document-content evidence, but introduces parsers or another model request, extra latency/cost and additional failure paths. Deferred.

## Scope and constraints

- Preserve the public Python3.11+ standard-library-only runtime and vanilla JavaScript UI.
- Add a server-side Decisions client and reusable routing policy/evidence module; continue using Responses for answers and tools.
- Keep existing fixed-model apps working. Routing is an app-owner setting, not a prompt-controlled setting.
- Preserve chat streaming, attachments, approved tools, structured output, failure atomicity, knowledge bindings and standalone launchers.
- Keep5-files/10MiB-per-file/20MiB-per-conversation intake limits unchanged.
- Initial routing covers application chat, including chat within Studio. The generator's own setup interpreter continues using its configured setup model. Never recursively route the router's requests.
- No paid PDF/Office extraction pass, automatic answer grading/regeneration, arbitrary provider routing, production hosting, or changes to the private repo in this version.

## Configuration and adoption

**Proposed:** creation offers Fixed model and Auto — cost-first in the model step. Existing/imported apps remain fixed unless their owner enables Auto. No app silently replaces an explicitly selected model.

The operator supplies a validated, nonsecret candidate policy through a local JSON configuration file. On selecting Auto, the builder embeds a validated snapshot in the application's optional `runtime.routing` settings. JSON imports can supply the same settings. Standalone exports carry this snapshot; they do not depend on the framework or its original configuration path.

The snapshot contains a policy version, router model, approved candidate model IDs, per-candidate capability declarations, tested capability tier, relative expected-cost rank, and an explicit balanced fallback model. Tiers are economy, balanced and advanced; candidate IDs are configured rather than invented by the classifier. Include context/output limits and support flags for document/image inputs, every enabled hosted/function tool, and structured output. Declare image-generation tools separately from image-input support. Every exported policy includes an appropriate document-capable fallback for its enabled inputs or fails validation.

Use reviewed cost ranks for the initial release; they represent expected workload cost and are not a claim to dynamically discover the cheapest market price. Do not fetch price pages or list all models on each chat request. Access/capability declarations must be verified during configuration/evaluation; listing a model ID alone does not establish tool access.

Missing, malformed or incompatible Auto configuration is an actionable configuration error. Fixed mode remains usable independently. No API key or credential is embedded in policy, manifests or exports.

## Routing evidence

The router considers the current request and the conversation, not just the latest sentence. Proposed evidence budget:

- Full current user text within the existing16000-character limit.
- App purpose/instructions as task evidence, capped at8000 characters.
- Most recent8 messages, capped at16000 characters combined; identify omitted older context.
- Names, server-determined MIME types, byte sizes and originating-turn position for all conversation attachments, including new files. Mark whether an excerpt is available.
- UTF-8 text excerpts for TXT, Markdown, JSON, CSV/TSV, YAML, XML, HTML and existing supported source-code formats: at most4000 characters per file and16000 characters combined. Prefer current-turn files; never silently label an excerpt as the whole document.

Do not parse PDF, DOC/DOCX, RTF/ODT, PPT/PPTX, XLS/XLSX or image contents for the routing pass. These supply metadata only. HTML/XML is untrusted text evidence, never executed, fetched, or expanded. Unreadable text remains metadata-only rather than failing an otherwise valid chat.

The answering model receives the original complete request, full retained conversation and original validated files through the existing Responses input path. Router evidence caps never truncate answering input. File byte counts are not token counts; unknown binary-document context usage must remain explicitly unknown.

## Selection flow

1. Validate the request, app and files; load the app-owned conversation and policy.
2. Filter approved candidates by all enabled tools, structured output, input types and configured output budget. Use conservative estimates for known text. For unknown binary-document context, use owner-approved document candidates/context bounds rather than asserting that exact fit was calculated. Provider context limits can still reject a request; surface those errors without silent truncation.
3. If no candidate is eligible, return an actionable error before any model call. If only one is eligible, use it without a redundant Decisions request and explain that rule in status.
4. Otherwise call `POST /v1/decisions` once. Current documented router model: `gpt-6-luna`. In one request ask two independent fixed-choice questions: required effort (economy/balanced/advanced/uncertain), and task category (extraction/summary/transformation/explanation/reasoning/coding/other). Dedicated routing instructions stay separate from untrusted app text, conversation and excerpts. The classifier cannot supply arbitrary model IDs, change credentials or override the candidate policy.
5. Validate typed answers and probabilities. Map the effort to the lowest-cost-ranked eligible candidate meeting that tier. Cost rank breaks ties within the required capability tier; use a stable model-ID tie break. If the requested tier has no eligible candidate, use the configured compatible fallback rather than guessing an unapproved model.
6. Proposed initial uncertainty rule: selected effort probability below0.65 or `uncertain` uses the configured compatible balanced fallback. This is a tunable policy threshold, not a calibrated answer-quality probability. Evaluate it on representative requests before claiming savings/quality levels.
7. Pin the selected answering model for the entire user turn, including function-call rounds. Reconsider on the next user turn, preserving full retained conversation.
8. Generate and stream the answer through the existing Responses client; save the turn plus bounded routing metadata only after the existing successful/usable-partial completion rules pass.

## Routing failures

Proposed router timeout:2 seconds, configurable within0.5–10 seconds. A transient router timeout/connection/5xx error uses the configured compatible fallback once and marks the routing reason accurately. An invalid answer or unsupported category uses the same explicit fallback with an invalid-decision reason.

A Decisions refusal, authentication/permission failure, or exhausted billing/quota is surfaced explicitly rather than treated as a successful classification. Do not cycle models for exhausted quota. Final Responses failures retain existing actionable diagnostics; do not automatically replay a turn after streamed text or executed tools. No automatic second-answer escalation in this release.

Cancellation/disconnection during routing must prevent starting an answer request once cancellation is known. No failed/unconfirmed turn becomes saved history. A failed routing/answer status may remain visible as an unsaved attempt, while the draft/files remain available to retry.

## Conversation compatibility

Current `runtime.py` fingerprints the app together with its selected model. Under Auto, fingerprint the app and routing-policy snapshot, excluding the model chosen for an individual turn. Fixed mode keeps its existing fingerprint behavior, including protection against changed environment defaults. Changing app instructions or the policy still requires a new conversation. Enabling Auto on an existing app starts new conversations; no database rewrite is required.

Saved assistant messages gain a bounded optional routing record. Legacy messages without it still load. Routing metadata is not replayed as user instructions or answering-model content.

## Routing status and history

Show an accessible Routing status section near chat status, with compact default content and expandable details. Keep the existing bottom-left application version/build label separate.

Always distinguish the answer model from the Decisions router model. Show selecting-model progress, chosen answer API model ID, route, short explanation and fallback status. After completion use the model ID reported by Responses if present; otherwise label it as the requested model ID rather than claiming an unreported identity. Validate/bound provider model IDs before display.

Example summary: “Economy route: routine extraction. This lower-cost approved model meets the configured document and tool requirements.” Construct explanations from validated typed classifications and applied rules. Do not fabricate a prose explanation allegedly returned by Decisions or make another generative call to write it. A metadata-only PDF route must never claim to have inspected its contents.

Details can show policy version, router model, decision probabilities, evidence coverage/truncation, model-selection/answer timings, and separate router/answer token usage. Candidate cost ranks are not dollar-cost receipts. Restore each saved turn's status on history load. A fallback explanation must say why the preferred route was not used. Do not silently leave a previous turn's model displayed while selecting the current model.

Store the compact routing record with the turn in existing local SQLite history. No new raw-prompt logging or secondary copy of document excerpts is introduced. Sensitive data remains subject to the existing local-history privacy behavior.

## Packaging and validation

Add router modules to explicit standalone/package/Docker allowlists. Generated app UI includes Routing status and embedded policy; keys remain runtime environment settings. Update README architecture, APIs, configuration, limits, release notes and generated-app instructions; bump the public release and preserve immutable export build IDs.

Offline tests cover effort/task mapping, candidate filtering, file-only/follow-up evidence, truncated/unreadable text, metadata-only binary inputs, injection-like document text, invalid/refused Decisions answers, timeout/cancellation, billing diagnostics, fixed-mode compatibility, model switches across turns, tool-round pinning, routing history/status, and clean exports. Test the actual Responses/Decisions request boundaries with recorders. Run the full existing Python/JavaScript suites and Docker checks; browser-check framework/generated apps and mobile status readability.

Before enabling a recommended pool for real use, compare it with a fixed-model baseline on a labeled mix of simple, complex, tool and document requests. Track answer usefulness/error rate, task success, total router-plus-answer token cost, fallback/retry frequency and end-to-end latency. Some quality variation is accepted; neither a specific savings percentage nor a universal best model is promised. Live evaluations need the user's authorized API access and incur charges; none are needed to review this design.

## Builder discretion

Module/function names, bounded metadata schema, status styling, validation helpers and fixture organization are implementation choices. Keep them consistent with the public framework. Initial candidate model IDs/access and cost ranks require reviewed configuration/evaluation, not guesses made by a language classifier.

## Official API references

Checked2026-11-15: [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) and [create decision reference](https://developers.openai.com/api/reference/python/resources/decisions/methods/create). Decisions supports typed choices and conversation evidence, with file inputs excluded; the application's extraction boundary above is deliberate. Recheck provider access/capabilities before live implementation tests.
