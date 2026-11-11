# Chat attachments implementation plan

Goal: support multi-file selection and drag/drop in public Studio chat/setup and every new standalone export, sending content alongside typed text.

Design: shared dependency-free attachment validation/payload helpers; inline Responses input_file/input_image content, no Files or vector-store creation. Store accepted chat attachments inside private session history for follow-ups, expose filenames/sizes only to UI. Bound requests and cumulative conversation attachment bytes. Setup files are current-step input; clarification retains the queued files. Preserve exact UTF-8 instructions and actual Action JSON rather than inventing configuration from binary documents. Inline attachment limits:5 files,10 MiB each,20 MiB total per turn and conversation. Use existing server credentials/models and offline recording providers for verification.

- [x] Add failing validation/runtime/setup/HTTP/export tests, including failure atomicity, limits and sanitized history.
- [x] Implement shared server intake, multimodal runtime history, setup intake and export dependencies.
- [x] Add accessible picker, tray, whole-chat file drag/drop, retry retention and navigation cleanup; add JS behavior tests.
- [x] Document API/data handling, file/model limits, setup semantics and exports; update release/build identification.
- [x] Run full Python/JS suites, build/package verification and browser checks for Studio and exported standalone app; commit/push public repository.

Review focus: unsupported/malformed/path filenames rejected before provider; attachment-only messages; accumulated limits and file history replay; failed streams preserve draft and never save a turn; no file bytes in session endpoints or app ZIPs. Text-only clients remain compatible. Instructions accept UTF-8 text/code files exactly; binary instruction documents require a text export, with actionable guidance.

## Verification and review

100 Python unittest tests passed with GPTAPPS_TEST_DOCKER=1, including both real Docker launcher tests;13 dependency-free JavaScript tests passed. Wheel0.1.1 includes the shared Python/JS intake and excludes unrelated local directories. Public and generated Docker images include attachment assets; generated Docker metadata matches its immutable export build.

Offline HTTP recording verified exact bytes of multiple files plus typed text, requests above the previous1.5MB limit, follow-up replay, metadata-only history, validation before provider calls, and Studio setup context. Actual browser verified multi-file selection, stream-failure retry preservation, successful streamed turn, a file-only standalone message and390px phone layout. No real OpenAI requests or personal document uploads were made.

Independent review found a knowledge-to-Actions queue leak. Two failing regressions reproduced it; chat intake is now disabled in the permanent-knowledge step and Use these files clears queued transient files/text. Focused re-review found no remaining important issue. Live provider acceptance/quality remains model/account-dependent and was not tested.
