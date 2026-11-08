# Knowledge uploads

The framework must let an owner select multiple local knowledge files, upload them to OpenAI, index them, and produce an app with working `file_search` bindings. Keep credentials server-side and retain the existing Python 3.11+ standard-library runtime and shared UI.

## Approach

Use the Files API and Vector Stores file batches. Responses `file_search` consumes the resulting store; Agents API is unnecessary. The browser sends selected files one at a time through the local framework server, which forwards them to OpenAI. This avoids loading an entire multi-file multipart request into memory or exposing the API key. A persisted upload record provides progress and recovery after a browser reload. No source document content is kept on disk by the framework.

An inventory-only change would leave the existing blocker. Direct browser-to-OpenAI requests would expose credentials. The selected approach implements the complete upload/index/bind workflow within the authorized feature request.

## UI and behavior

- Show a multiple-file picker at the knowledge setup step, with filenames, upload/indexing progress, and an explicit Upload and index action.
- Offer the same panel through Knowledge files in the builder sidebar for existing apps. Standalone apps retain retrieval, with builder upload controls and endpoints disabled.
- Allow up to 100 supported files per collection, 25 MiB per file, and 100 MiB total. Explain these framework limits and that OpenAI storage/usage charges may apply.
- Persist upload metadata, provider IDs, and status under the ignored data directory. Offer recent uploads in the panel so a reload does not require uploading successful files again. Do not retry uncertain provider mutations automatically.
- Enable Use these files only after every selected file has indexed successfully. Setup carries an opaque upload ID into app creation; the server verifies readiness and fills filenames and vector store bindings. Existing app attachment explicitly replaces its knowledge collection; previous OpenAI resources are retained.
- Existing manual manifests and no-knowledge replies continue working. No document contents become setup instructions. Uploads are retained in the OpenAI project even if setup is cancelled; the UI/docs explain this and account-side cleanup.

## Boundaries

Only fixed OpenAI API endpoints receive the server key. Validate extensions, sizes, names, upload IDs, file slots, and terminal indexing counts. Reuse sanitized provider diagnostics. A failed collection cannot unblock an app. Partial batches, unknown uploads, cross-origin calls, duplicate indexing, standalone mutations, and app configuration changes during binding must be handled explicitly. Never delete existing OpenAI files/stores automatically.

## Verification

Use fake provider HTTP boundaries for multipart payloads and API failures; persistent manager tests for multiple files, resume, indexing failures, and bindings; local HTTP tests for generated ZIP bindings and standalone denial; real browser interactions for selection, progress, ready/failed states, and app creation. Run the full Python suite including Docker and the Node tests. Live uploads require the owner's selection and configured key; tests do not transmit private files.
