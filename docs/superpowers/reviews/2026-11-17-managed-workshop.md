# Managed Workshop implementation review

Reviewed range: `345ee496308563748ec1e77ac7bc325cfc64cdcf..6c7cf323e6c8f4a3582053cf7cdf3c79c24ab6ac`.

One independent, read-only whole-branch review inspected configuration, the SDK contract, lifecycle/storage, tools/knowledge/artifacts, UI, packaging and evaluation behavior against the approved design. No critical findings. Four functional findings and one operational-documentation finding were reproduced and fixed in one pass.

| Finding | Correction | Regression evidence |
| --- | --- | --- |
| Unsent follow-up could bind the previous completed turn after restart | Recovery distinguishes durable send intent from an inherited provider session ID; stale previous-turn events cannot identify the new turn | Queued/preparing follow-up restart tests and unknown-send test failed before the fix and pass afterward |
| Early EOF could abandon a follow-up worker and its deadline | Nonterminal EOF enters bounded reconciliation; deadlines inspect durable active work and can resume cancellation observation without a live worker | EOF reconnect and missing-worker deadline tests failed before the fix and pass afterward |
| Leaving work could leave the composer busy; late callbacks could overwrite the new view | New conversations explicitly restore idle controls; generation/app guards protect acceptance and result-snapshot continuations | Actual-function Node interaction tests failed before the fix and pass afterward; browser confirmed an editable new draft after Leave task running |
| Definite rejection could become a persistent nonexistent task | Preserve HTTP status, confirm lookup absence, remove the marker and restore draft/files for definitive nonacceptance; ambiguous transport outcomes still reconcile | Rejection and ambiguous-transport interaction tests; browser verified a missing-SDK rejection leaves the original request editable |
| Generated Agents README described Responses/storage incorrectly | Select Agents architecture, Vector Stores Search, managed storage and recovery/retention guidance by runtime | Exported README assertions failed before the fix and pass afterward |

The reviewer classified the README issue as minor. The implementer treated it as important because it supplied incorrect API, storage and recovery instructions to standalone-app operators. No review finding remains deferred.

## Final verification

- Python 3.14: **225 tests passed**, with real Docker builds/startup/persistence and optional pinned-SDK launcher/image checks enabled.
- Python 3.11: **225 tests passed**, with six explicitly opt-in Docker/SDK checks skipped.
- Node built-in runner: **35 tests passed**; no npm dependencies.
- Synthetic browser checks: Studio runtime selection/save, standalone streaming/progress, reload/recovery, history, download, mobile layout and execution receipt; post-review Leave and rejection interactions checked again.
- Official `openai==3.13.0` installed in an isolated temporary environment; Agents namespace and session/events/artifact/environment-file signatures checked without API requests.
- `git diff --check` clean. Exports use an explicit runtime allowlist; local data/credentials are excluded.

## Verification boundaries

The reviewer declined to assess actual project/model/tool access, live service behavior and semantic quality/cost/document fidelity without credentials and behavioral runs. This stands: no live API access or production quality is claimed, and behavioral release remains on hold. Cost if wrong: real project access or output quality can differ from fixtures and SDK shape checks.

The reviewer also did not independently rerun all Docker/dependency/browser checks in its sandbox. The implementer ran those checks directly with the required socket/Docker permissions and recorded the results above. Cost if wrong: the independent review verifies source and targeted reproductions, while broader environment evidence comes from the implementation session.

The four functional reproductions and documentation assertions were verified RED → GREEN; the complete suites passed after the fix pass. No second review seat was added. This is engineering evidence for an experimental feature branch, not approval of production behavioral quality.
