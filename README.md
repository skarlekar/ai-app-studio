# GPT Application Framework

Convert Custom GPT configurations you own into standalone Python chat applications powered by the OpenAI API.

Create an application through AI-assisted setup, or import an owner-provided JSON export. Review compatibility, try the app locally, and download a self-contained application folder or ZIP.

Explore the [AI App Studio companion page](https://ai-app-studio-introduction.peppyshrimp1.chatgpt.site) for the walkthrough and architecture, or read the [illustrated introduction](docs/launch/illustrated-introduction.md).

**Status:** local, single-user prototype. The framework provides configuration migration and a shared runtime. It does not guarantee identical behavior to the original GPT or provide production hosting.

- **Python:** 3.11+; the Docker image includes Python 3.13.
- **Runtime dependencies:** Responses uses the Python standard library; optional Agents support pins `openai==3.13.0`; browser Markdown/sanitizer libraries are bundled locally.
- **License:** [MIT](LICENSE).

## Contents

- [Release notes](#release-notes)
- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Run with Docker](#run-with-docker)
- [Configuration](#configuration)
- [Managed Workshop: optional Agents runtime](#managed-workshop-optional-agents-runtime)
- [Auto — cost-first routing](#auto--cost-first-routing)
- [Ways to use the framework](#ways-to-use-the-framework)
- [Run a generated application](#run-a-generated-application)
- [Architecture](#architecture)
- [Attach files to chat](#attach-files-to-chat)
- [OpenAI APIs and tools](#openai-apis-and-tools)
- [Application format](#application-format)
- [Knowledge files and Actions](#knowledge-files-and-actions)
- [Extensions](#extensions)
- [Local HTTP interface](#local-http-interface)
- [Privacy and public repositories](#privacy-and-public-repositories)
- [Limitations](#limitations)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [License](#license)

## Release notes

### 0.3.0 — 2026-11-17 (feature branch)

- **Two explicit runtimes:** keep Responses with Fixed/Auto routing, or select Agents API with a fixed model and an optional OpenAI-hosted workspace. Setup can suggest a runtime; owners confirm the choice. Legacy apps keep their existing behavior.
- **Managed work:** durable submission/run IDs, browser-independent execution, saved progress events, reconnection, restart reconciliation, confirmed cancellation and deadlines. Unknown outcomes are surfaced without silently resubmitting paid work.
- **Reviewable deliverables:** stage chat inputs, bridge app-bound knowledge through Vector Stores Search, execute explicitly replay-safe read tools, and validate completed-turn artifact downloads with ownership/path/size limits.
- **Portable optional dependencies:** `./start.sh --agents` uses a dedicated virtual environment; `./docker-start.sh --agents` includes the pinned SDK in the image. Agents exports automatically carry their dependency metadata and launch support. Both runtimes retain the bottom-left version/build.
- **Lifecycle and evaluation:** seven inactive days of managed session/artifact retention by default, explicit owned-resource cleanup, retryable remote deletion, private comparison reports and a human-reviewed release check. Development chat/downloads stay experimental; mock tests do not certify model quality.

See [Managed Workshop](docs/managed-workshop.md) for configuration, provider permissions, recovery, limits, APIs and evaluation commands. This branch does not change the default runtime or introduce a frontend-code-generating agent.

### 0.2.2 — 2026-11-15

- **Prompt-specific routing explanations:** the sidebar describes the actual requested task and its demands, alongside the server's model-selection rule, instead of only showing “Required effort classified.”
- **Separate assessment and policy facts:** Decisions still classifies effort/task. After a normal classification, one bounded Responses request creates a brief public assessment; it cannot change the chosen model. Fixed, sole-candidate and fallback selections keep their factual policy reasons without this extra call.
- **Visible overhead and reliable answers:** explanation model, usage, time and availability appear separately from classifier/answer usage. A 3-second transport timeout, 512-output-token limit, no tools and no retries bound the extra work. Unavailable/invalid/refused explanations leave the original selection and first answering attempt intact.
- **Portable history and exports:** new saved turns retain the assessment. Older records remain readable without generating paid explanations on load. Newly exported apps include the same behavior. See [Attachment evidence, status and cost](#attachment-evidence-status-and-cost).

### 0.2.1 — 2026-11-15

- **Auto routing ready at startup:** `./start.sh` and `./docker-start.sh` load the bundled `routing-policy.json` by default, so selecting Auto no longer requires an extra launch option.
- **Configurable policy:** use `--routing-policy FILE` to override the starter; an existing `OPENAI_ROUTING_POLICY_FILE` environment setting is also honored. Explicit flag > nonempty environment > bundled starter. Docker mounts the selected host file read-only.
- **Starter model pool:** economy Luna, balanced/fallback Sol, advanced Astra. Review model/tool access and workload quality/cost before live use. Existing saved applications keep their configured model/policy snapshots; Auto remains an explicit app-owner choice.

### 0.2.0 — 2026-11-15

- **Optional Auto — cost-first routing:** choose an approved answer model for each app-chat turn from an operator-reviewed policy. Existing apps keep their fixed-model behavior. The setup interpreter still uses its configured setup model.
- **Attachment-aware selection:** classify bounded conversation/app text, attachment metadata and available UTF-8 excerpts with Decisions; stream the answer and tools through Responses with the original full inputs. Binary documents and images supply metadata only to the routing pass.
- **Sidebar routing status:** below Recent Conversations, show the answer model, route, short rule-based explanation and fallback reason; expand details for the separate router model, evidence coverage, timings and router/answer usage. Successful saved turns retain this information.
- **Portable Auto apps:** generated apps include the validated policy snapshot, routing runtime and status UI. They need an API key with the required model/tool access, but do not need the original policy file or an `OPENAI_MODEL` setting.
- **Configuration release:** the new optional `runtime.routing` setting, policy-file configuration and routing status events extend the public contract, so this release advances to 0.2.0. See [Auto — cost-first routing](#auto--cost-first-routing) for setup, cost reasoning and limits.

### 0.1.2 — 2026-11-13

- **Bottom-left version and build label:** the framework and generated standalone apps keep their release identifier visible at the bottom-left corner. Desktop placement sits below the sidebar history notice; mobile placement reserves space beneath the chat controls.
- **Release documentation:** this README now records release highlights and upgrade instructions.

### 0.1.1 — 2026-11-11

- **Chat attachments:** select multiple files or drag them into chat, review/remove the selected files, and send their contents together with your typed message. File-only messages also work. The shared UI and runtime include this feature in newly generated standalone apps.
- **Supported inputs and limits:** documents, spreadsheets, text/code, and PNG/JPEG/WebP images; up to 5 files per message, 10 MiB each, and 20 MiB combined per message and conversation. The configured model must support the chosen input types. See [Attach files to chat](#attach-files-to-chat) for formats, setup behavior, and provider limitations.
- **Follow-ups and recovery:** accepted files stay with local conversation history and are replayed on follow-up turns. Interrupted or failed requests retain the draft and selected files for retry. Chat attachments remain separate from permanent knowledge collections.
- **Setup protection:** UTF-8 instruction files preserve their supplied text, and Action JSON keeps supplied definitions rather than inventing schemas. Transient attachments cannot carry over from the permanent-knowledge step into Actions.
- **Build identification and packaging:** added version/build labels, immutable standalone build numbers, and attachment assets in Python/Docker packages. Package discovery explicitly excludes unrelated local directories.

**Upgrade:** run `git pull --ff-only` in your framework checkout, then restart `./start.sh` or rebuild/restart with `./docker-start.sh` and refresh the browser. **Download a fresh standalone export for existing generated apps** to receive the latest UI/runtime. Keep your existing app configuration, API settings, and private data directory. A framework update does not modify previously downloaded app folders.

## What it does

| Feature | Behavior |
| --- | --- |
| AI-assisted setup | Interprets natural-language replies, validates settings, and asks about ambiguous answers |
| JSON import | Normalizes a supported owner-provided export into a versioned application manifest |
| Compatibility checks | Separates blocking dependencies from suggestions for behavior review |
| Standalone builds | Packages one app with its backend, web UI, configuration, and compatibility report |
| Chat | Streams live responses and renders Markdown, with local conversations, attachments, citations, generated images, and selected hosted tools |
| Optional model routing | Selects a policy-approved answer model per turn, with visible reasons and separate routing/answer usage |
| Knowledge files | Uploads multiple selected documents to OpenAI, indexes a vector store, and binds a fully ready collection to an app |
| Optional managed execution | Explicit Agents sessions, task recovery and validated downloadable artifacts |
| Backend extensions | Calls explicitly registered, read-only Python functions |
| Local and Docker launchers | Starts the builder, waits for readiness, and opens the correct browser URL |

The original GPT is unchanged. A public GPT URL or name cannot provide its private instructions, files, or Action definitions.

## Quick start

### 1. Get the source

Clone the public repository and open its folder:

```sh
git clone https://github.com/skarlekar/ai-app-studio.git
cd ai-app-studio
```

You can also download and extract the repository ZIP from GitHub, then open a terminal in the extracted folder.

### 2. Start the framework

On macOS, Linux, or a Bash-capable environment with Python 3.11+:

```sh
./start.sh
```

The launcher:

1. Finds a supported Python interpreter.
2. Uses your existing `OPENAI_API_KEY` and `OPENAI_MODEL`, or prompts for them in the terminal.
3. Hides the key while you type and keeps it only in the process environment for this run.
4. Creates local app and history directories if needed.
5. Starts the framework and opens [http://127.0.0.1:8765](http://127.0.0.1:8765) after the server is ready.

Leave the terminal open. Press **Ctrl+C** to stop the server. `./run.sh` is an alias for the same launcher. If executable permissions were lost during download, run `bash start.sh` instead.

AI-assisted setup and app conversations require an OpenAI API key and an API model available to your project. The setup model must support the Responses API and Structured Outputs. The app model must support its selected tools. API usage is billed to your API project; ChatGPT subscription access does not configure this server's API access.

### 3. Create an application

Choose **Create application** and provide:

1. Name and description.
2. Full GPT instructions.
3. Conversation starters.
4. Enabled capabilities: web search, image generation, and/or code interpreter.
5. Fixed app model ID/server default, or **Auto — cost-first** when a routing policy is configured.
6. Knowledge filenames, if any.
7. Action definitions, if any.
8. A final review and instruction to create the app.

You can answer naturally:

| Step | Example reply | Result |
| --- | --- | --- |
| Name | “Call it Spanish Teacher” | Extracts the application name |
| Starters | “No conversation starters needed” | Empty starter list |
| Tools | “Enable web search but no images or code” | Web search only |
| Model | “Use the default model” | Uses the server's fixed app model |
| Model | `auto` or the **Auto — cost-first** button | Embeds the configured routing policy for per-turn model selection |
| Knowledge | “I don't have any knowledge files” | Empty inventory; no vector store needed |
| Actions | “No actions are required” | Empty Action list |
| Ambiguous reply | “I'm not sure about files” | Asks a follow-up without advancing |
| Final review | “Looks good, go ahead” | Saves the reviewed application |

The AI interprets one guided step at a time. GPT instructions remain verbatim, and actual Action JSON schemas are parsed directly rather than rewritten by the model. Other interpreted values pass through server validation before being accepted. Review the summary, especially enabled tools, filenames, and model selection.

Use `back` to revise the previous step and `cancel` to leave setup. Shift+Enter inserts a newline. Drafts live in the browser until creation; reloading discards an unfinished draft. AI/API failures keep the current step and draft so you can retry.

The guided setup also provides Back and Cancel setup buttons near the composer. Navigation is disabled while an answer is being interpreted. Create application is the main action in the builder; New conversation is the main action in generated apps. On smaller screens, the Conversations button opens saved history.

### Launcher options

```sh
./start.sh --port 9000
./start.sh --apps migrated/apps
./start.sh --apps apps --data .gptapps-data --no-browser
./start.sh --routing-policy /path/to/custom-policy.json
./start.sh --help
```

Both framework launchers use the bundled [routing-policy.json](routing-policy.json) automatically. Supply `--routing-policy FILE` only to choose another policy file; a nonempty `OPENAI_ROUTING_POLICY_FILE` environment setting also overrides the bundled default. The explicit flag takes precedence over that environment setting. The bundled path resolves from the framework root even when launching from another directory.

The default catalog is `apps/`. Use `--apps migrated/apps` to open configurations created by earlier versions of the framework. Relative directory options are resolved from the framework root, even if you launch the script from another directory. An occupied port produces an error; the launcher does not stop another process.

## Run with Docker

Docker runs the Python backend in a container, so you do not need Python installed on the host. Install and start Docker Desktop, or use a working Docker Engine installation with Bash.

```sh
./docker-start.sh
```

The Docker launcher prompts for missing settings, builds the image, starts the builder, waits for the container's health check, and opens the browser. Press **Ctrl+C** in the launcher terminal to stop and remove its container.

```sh
./docker-start.sh --port 9000
./docker-start.sh --apps migrated/apps --no-browser
./docker-start.sh --routing-policy /path/to/custom-policy.json
./docker-start.sh --help
```

### Default routing policy in Docker

A starter [routing-policy.json](routing-policy.json) is included in the repository. It uses Luna for economy, Sol for balanced/fallback, and Astra for advanced requests, with the same example capability declarations as the documented policy. Review model/tool access in your OpenAI project and adjust the candidates before live use; policy validation does not check account access or measure savings.

After updating from 0.2.0, stop the current Docker launcher with **Ctrl+C**, then restart from the repository folder. The starter policy is now loaded without a flag:

```sh
./docker-start.sh
```

The launcher mounts the selected host policy read-only at `/config/routing-policy.json` and sets `OPENAI_ROUTING_POLICY_FILE` **inside the container**. No manual container editing or environment export is needed. To use another file, run `./docker-start.sh --routing-policy /path/to/custom-policy.json`. The same default/override behavior applies to `./start.sh`. Selecting Auto is still a separate choice during app setup; starting with the policy does not change fixed-mode apps.

Keep the browser tab open to retain an unfinished setup draft; after the server restarts on the same port, type `auto` and send again. The Auto button's availability is loaded when the page opens, so it may remain disabled in an already-open tab; a page reload updates it but discards an unfinished draft. For a new setup, select **Auto — cost-first** at the model step. Existing apps retain their previously saved model/policy snapshots.

| Component | Location |
| --- | --- |
| Python runtime | Official `python:3.13-slim` base image; build verifies Python 3.11+ |
| Application source | `/app/gptapps` inside the container |
| Application manifests | Host `apps/` mounted at `/data/apps` |
| Conversations and generated images | Host `.gptapps-data/` mounted at `/data/runtime` |
| API credentials | Passed from the launcher's environment; excluded from image builds |
| Routing policy | Bundled `routing-policy.json` (or operator override), mounted read-only at `/config/routing-policy.json` |
| Browser access | Host `127.0.0.1:PORT`, published to the same container port |

App configurations and history survive container removal because they are bind-mounted from the host. The launcher runs the container with your host user/group IDs to keep these files usable outside Docker. The image itself defaults to a non-root numeric user. `GPTAPPS_DOCKER_IMAGE` and `GPTAPPS_CONTAINER_NAME` can override the default image tag and container name.

The backend binds to `0.0.0.0` **inside** the container so port publishing can reach it. The launcher publishes only to `127.0.0.1` on the host, following Docker's [localhost publishing syntax](https://docs.docker.com/engine/network/port-publishing/). The browser's port and the backend port must match because Host/Origin validation uses that port.

To build and run manually, first export `OPENAI_API_KEY` and `OPENAI_MODEL` in your shell, then:

```sh
mkdir -p apps .gptapps-data
docker build -t gpt-app-framework:local .
docker run --rm --init \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:8765:8765 \
  -e OPENAI_API_KEY -e OPENAI_MODEL -e OPENAI_SETUP_MODEL \
  -e OPENAI_ROUTING_POLICY_FILE=/config/routing-policy.json \
  -v "$PWD/apps:/data/apps" \
  -v "$PWD/.gptapps-data:/data/runtime" \
  -v "$PWD/routing-policy.json:/config/routing-policy.json:ro" \
  gpt-app-framework:local
```

The Docker build copies only the runtime source, public example, entrypoint, and license. `.dockerignore` excludes local credentials, private GPT exports, and application history from the build context. No model or key is baked into the image.

## Configuration

| Environment variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Server-side OpenAI project key | Required for live AI requests |
| `OPENAI_MODEL` | Default model for fixed apps; fallback model for setup | No hardcoded model |
| `OPENAI_SETUP_MODEL` | Separate model for interpreting setup replies; must support Structured Outputs | `OPENAI_MODEL` |
| `OPENAI_ROUTING_POLICY_FILE` | JSON policy offered for Auto creation; `--routing-policy FILE` overrides this setting | Launchers: `routing-policy.json` under the framework root; direct CLI: unset |
| `GPTAPPS_PORT` | Port used by either launcher | `8765` |
| `GPTAPPS_APPS_DIR` | Launcher app catalog directory | `apps/` under the framework root |
| `GPTAPPS_DATA_DIR` | Launcher conversation/asset directory | `.gptapps-data/` under the framework root |
| `GPTAPPS_PYTHON` | Local launcher's Python executable name or full path | Supported `python3`, then `python` |
| `GPTAPPS_DOCKER_IMAGE` | Docker image tag | `gpt-app-framework:local` |
| `GPTAPPS_CONTAINER_NAME` | Docker container name | `gpt-app-framework-PORT` |

### Model examples

`OPENAI_MODEL` powers fixed-model conversations in converted apps. `OPENAI_SETUP_MODEL` interprets the framework's setup replies, so it can usually be a smaller, less expensive model. These are starting points to evaluate with your own GPTs:

| Use case | `OPENAI_MODEL` | `OPENAI_SETUP_MODEL` |
| --- | --- | --- |
| Balanced app capability with economical setup | `gpt-6.1-sol` | `gpt-6-luna` |
| Simple chat apps and lower-cost experimentation | `gpt-6-luna` | `gpt-6-luna` |
| More demanding reasoning in the converted app | `gpt-6-astra` | `gpt-6-luna` |
| More capable interpretation of complicated setup replies | `gpt-6.1-sol` | `gpt-6.1-sol` |

OpenAI documents Responses API and Structured Outputs support for [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), and [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra). Their model pages also list supported hosted tools. Check your API project's access and the particular tool combination you enable; these examples do not guarantee availability or behavior parity.

For a balanced starting configuration:

```sh
export OPENAI_MODEL="gpt-6.1-sol"
export OPENAI_SETUP_MODEL="gpt-6-luna"
./start.sh
```

The launcher will prompt securely for the API key if it is missing. The same settings work with Docker:

```sh
export OPENAI_MODEL="gpt-6.1-sol"
export OPENAI_SETUP_MODEL="gpt-6-luna"
./docker-start.sh
```

To use one model for both roles, set `OPENAI_MODEL` and leave `OPENAI_SETUP_MODEL` unset. During conversion, answer “use the default model” to inherit `OPENAI_MODEL`, or supply an exact model ID such as `gpt-6.1-sol` for that app alone. Use API model IDs rather than display names from ChatGPT. Image-only, audio-only, and embedding models are not setup interpreter models.

A fixed app can set `runtime.model` in its manifest to override `OPENAI_MODEL`. An Auto app instead sets `runtime.model: null` and embeds its policy in `runtime.routing`. Neither changes the framework's setup interpreter model. The CLI's `--apps`, `--data`, `--port`, `--host`, and `--routing-policy` settings are command-line options; the `GPTAPPS_*` launcher defaults are not automatically read by the CLI.

[.env.example](.env.example) documents the settings. **The Python server and launchers do not automatically load `.env` files.** Use the launcher prompts or your normal environment/secret management. Never enter keys in GPT instructions, Action schemas, the web builder, or source control.

Importing JSON, analyzing manifests, and building application folders work without API credentials. Plain `serve` can also start without them, but live setup interpretation and app chat will fail until the required server environment is configured.

## Managed Workshop: optional Agents runtime

Responses remains the default. Choose Agents when the application needs managed multi-step work, a persistent workspace and downloadable results. Runtime choice and model routing are separate: **Agents initially requires one explicit fixed model**; Decisions Auto remains on Responses. Knowledge files and Actions do not automatically change runtimes.

```sh
./start.sh --agents
# Or use the Python 3.13 Docker image with the optional SDK included:
./docker-start.sh --agents
```

The local launcher installs `openai==3.13.0` in `.venv-agents`; normal Responses launches need no third-party Python packages. In setup choose **Agents API**, a supported fixed model (the official quickstart demonstrates `gpt-6-astra`), and **OpenAI-hosted workspace** or capability-limited **No workspace**. Confirm model access in your project. The key remains server-side. The hosted sandbox has network access disabled, automatic review, no Studio credentials and no external write adapters.

The shared UI shows task progress, saved execution receipts, safe download cards and release readiness. Reattach after a browser disconnect; leaving the browser does not cancel provider work. Seven-day inactive retention and explicit cleanup affect owned runtime resources, while shared knowledge stays intact. Agents data is stored in managed OpenAI sessions as well as private local records.

Read the [complete Managed Workshop guide](docs/managed-workshop.md) for the manifest example, fixed-model restrictions, app-scoped knowledge bridge, replay-safe tool registration, artifact limits, cancel/restart/unknown-outcome behavior, standalone launch examples and owner-reviewed evaluation gate. The first release is experimental; source-code generation, Agents Auto, multi-agent work and the private SSO experience designer are deferred.

## Auto — cost-first routing

Auto is an app-owner choice for application chat in both Studio and generated apps. Existing and imported apps stay fixed unless their owner explicitly adds a routing policy. Selecting Auto during creation does not route the generator's setup interpreter.

### Enable and embed a policy

Review the bundled [routing-policy.json](routing-policy.json), verify the candidate models and tools in your API project, then start with your usual launcher credentials/model settings. Both launchers use this file automatically:

```sh
./start.sh
# Or use Docker; the policy is mounted read-only automatically:
./docker-start.sh
```

For a different policy, the flag overrides the default (and any inherited policy environment setting):

```sh
./start.sh --routing-policy /path/to/custom-policy.json
./docker-start.sh --routing-policy /path/to/custom-policy.json
```

You can also set `OPENAI_ROUTING_POLICY_FILE=/absolute/path/policy.json` in the launcher's environment. Precedence is **explicit flag > nonempty environment setting > bundled starter**. [examples/routing-policy.example.json](examples/routing-policy.example.json) remains available as a separate editable reference. Direct CLI commands do not apply launcher defaults; supply the policy explicitly:

```sh
python3 -m gptapps serve --builder --apps apps --data .gptapps-data \
  --routing-policy routing-policy.json
```

At the model step choose **Auto — cost-first** or type `auto`; **Fixed — server default** and exact fixed model IDs remain available. Creation validates and embeds a snapshot under `runtime.routing`, with `runtime.model` set to `null`. You can also supply that validated snapshot in a canonical app manifest. The launchers reject missing or unreadable policy files before startup. A readable policy that fails validation leaves Auto unavailable with an actionable error; fixed-mode use remains available. Direct CLI `--routing-policy` validates the file before starting its server. The policy is configuration, not a place for API keys or prompts.

The server policy file controls new Auto snapshots. Editing it does not silently change existing app manifests or exports. To change an app's policy, edit its manifest, restart its server and start a new conversation. A standalone Auto export contains the snapshot and needs neither the original file nor `OPENAI_MODEL`; it still needs your runtime API key and project access.

| Policy field | Meaning |
| --- | --- |
| `mode`, `version` | `cost_first` and an owner-chosen policy version |
| `router_model` | `gpt-6-luna` for this release's Decisions classifier |
| `timeout_seconds` | Routing timeout, default 2 seconds; allowed range 0.5–10 |
| `min_probability` | Selected effort probability threshold, default `0.65`; a routing rule, not an answer-quality score |
| `document_context_floor` | Owner-approved context allowance per binary document/image, default 32,768; exact usage remains unknown |
| `fallback_model` | Explicit balanced/advanced candidate with text, document and image support; must be eligible for the request |
| `candidates` | 1–32 approved records with exact `model`, `tier`, `cost_rank`, `context_window`, `max_output_tokens`, and `capabilities` |

Candidate tiers are `economy`, `balanced`, and `advanced`. Lower nonnegative integer cost ranks express the owner's expected relative workload cost within a tier. Capabilities are `text`, `documents`, `images`, `web_search`, `image_generation`, `code_interpreter`, `file_search`, `function_calling`, and `structured_output`; image input and image generation are separate declarations. Unknown fields, duplicate model IDs and invalid limits are rejected.

The example assigns Luna/Sol/Astra to economy/balanced/advanced with ranks 0/10/20 and Sol as fallback. These tiers and ranks are example policy choices requiring your own account and quality checks. The official [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [Sol](https://developers.openai.com/api/docs/models/gpt-6-sol), and [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) pages were checked on 2026-11-15 for text/image input, Structured Outputs, function calling and the listed hosted tools. The example conservatively uses their published 922,000 maximum input tokens as `context_window`, below their 1,050,000 total context, and 128,000 maximum output tokens. A declaration does not grant model/tool access or establish quality for your tasks; verify it before live use.

### How a turn is selected

The runtime filters the approved pool by the request's input types, every enabled tool, structured output and context/output budget. If only one candidate is eligible, it skips Decisions. Otherwise one `POST /v1/decisions` request asks two typed-choice questions: effort (`economy`, `balanced`, `advanced`, `uncertain`) and task category (`extraction`, `summary`, `transformation`, `explanation`, `reasoning`, `coding`, `other`). The classifier cannot return an arbitrary answering model. Local rules select the lowest sufficient eligible tier, then lowest cost rank, with model ID as a stable tie-break.

An uncertain/invalid decision, effort probability below the threshold, unavailable effort tier, or transient router timeout/connection/5xx failure uses the configured compatible fallback and states why. No eligible candidate or incompatible fallback is a configuration error. Authentication, permission, exhausted quota and Decisions refusals surface explicitly. The runtime does not retry with a second answering model after an answer/tool failure.

The chosen answer model stays pinned for the whole user turn, including function-call rounds. The next turn can select another model while preserving the retained conversation. Auto conversation fingerprints bind the app and policy snapshot rather than a turn's chosen model; instruction/policy changes require a new conversation. Fixed-mode fingerprints retain their existing model checks.

### Attachment evidence, status and cost

Routing considers the full current message (within the existing 16,000-character limit), up to 8,000 app-purpose/instruction characters, and the last eight messages capped at 16,000 characters combined. All retained/current attachments contribute filename, server-determined MIME type, size and originating-turn metadata. Readable UTF-8 text/code contributes at most 4,000 characters per file and 16,000 total, preferring current files. Excerpts and omitted history are identified as such. App text, history and document text are untrusted evidence and cannot change the policy.

PDF, Office documents, RTF/ODT and images provide **metadata only** during routing; this release does not extract or inspect their contents for classification or send those files directly to Decisions. The answer still receives the original full request, retained history and validated files through Responses. Routing evidence caps do not truncate answer input. Byte sizes are not token counts, and provider context limits can still reject an input. The existing 5-file, 10 MiB-per-file and 20 MiB-per-conversation intake limits are unchanged.

The accessible **Routing status** section sits in the left sidebar below **Recent Conversations** in both Studio and generated apps. On narrow screens, open **Conversations and routing** in the header to view it. The section shows selection progress, the answer model, route and a prompt-specific **Request assessment**, followed by the actual policy reason. For example: “Basic Spanish greetings for a beginner. Common greetings and translations need a short direct answer with little synthesis.” The policy then explains that the selected model has the lowest configured cost rank among eligible models meeting the classified effort. It labels the answer model as provider-reported when available and requested otherwise, separately from the Decisions router model. Expand details for the real applied policy rule, explanation availability, fallback reasons, evidence coverage, probabilities, model identities, timings and separate **classifier / explanation / answer** token usage. New saved turns retain their compact assessment and routing record; reopening history restores them without an API call. Older turns show that an explanation was not recorded. Raw routing excerpts are not copied into that record or new logs; the brief derived assessment is stored with the turn. The version/build footer remains separate.

For normally classified Auto requests, the runtime sends the same bounded text/metadata evidence to a separate tool-free **Responses API + Structured Outputs** request using `gpt-6-luna`, with `store: false`, `reasoning.effort: none`, at most 512 output tokens and a 3-second transport timeout. It returns a request description (up to 120 characters) and effort explanation (up to 180 characters). This is a generated public assessment, not internal model reasoning or proof of answer quality. It may be imperfect. Model selection is already complete, and the assessment cannot override it. Server-authored policy facts and metadata-only file limits stay visible. No PDF/Office/image contents are extracted for the explanation.

If the explanation times out, is refused, malformed or unavailable, the UI says so and retains the policy reason; it continues with the original answer model without an explanation retry. Fixed apps, sole eligible candidates and fallback routes do not request an assessment. Tool rounds and history loading do not generate another one. Known disconnections are checked before/after explanation generation, and failed chat attempts are not saved. No additional setup or policy-file change is required; restart Studio or regenerate existing standalone exports to receive the new code.

Cost-first routing aims to send routine work to an economical approved model while reserving higher tiers for harder tasks. It adds a classification call when several candidates are eligible and, for a normal classification, one additional short Responses explanation request before the answer. Both add latency and API usage. Evaluate **aggregate classifier plus explanation plus answer usage**, including cached/uncached input, reasoning/output, hosted tools, fallbacks and any user retries; token counts and policy cost ranks are not dollar receipts. Ranks are reviewed configuration, not live prices, and this release does not promise a savings percentage or universal quality level. Compare against a fixed-model baseline on representative simple, complex, tool and document tasks, measuring usefulness/task success, errors, total cost, fallback frequency and latency. Some quality variation may accompany savings. Consult current [API pricing](https://developers.openai.com/api/docs/pricing) and the [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) before a paid evaluation.

## Ways to use the framework

### AI-assisted conversion

Run `./start.sh`, choose **Create application**, answer the questions, and review the result. At the knowledge step, select multiple files, choose **Upload and index**, wait until all files are ready, and choose **Use these files**. The builder offers downloads for the full configuration and a standalone ZIP with the vector store binding included. Action definitions still need reviewed backend adapters.

### Import a JSON export

Try the included non-private example first:

```sh
python3 -m gptapps import examples/minimal-export.json --out migrated
python3 -m gptapps serve --apps migrated/apps --builder
```

For your own export, replace the input path with a file you own or are authorized to migrate. The destination must be new to avoid accidental overwrite. Output contains:

```text
migrated/
├── apps/
│   └── APP_ID.json
└── report.json
```

The supported format has a top-level `gpts` array. See [examples/minimal-export.json](examples/minimal-export.json) for a complete input. Each entry uses:

- Unique string `id`, nonempty `name`, and full `instructions`.
- Optional `description` and `conversation_starters`.
- Explicit `capabilities.items` entries with string `key` and boolean `enabled`.
- `knowledge.files` as filenames or file records with `name`/`filename`.
- `actions.count` and/or `actions.items` to record Action requirements.

Known capability keys are `web_search`, `image_generation`, and `code_interpreter_and_data_analysis`. Unknown enabled capabilities become blockers. Other export formats need an explicit adapter that produces the same application contract.

Bulk import copies file names and Action counts/IDs. It deliberately does not copy opaque Action authentication objects or schemas. Add reviewed, credential-free schemas through conversational setup or a source adapter.

### Check compatibility

```sh
python3 -m gptapps check migrated/apps/APP_ID.json
```

Replace `APP_ID` with an actual filename from the import. A check exits with code **2** for deterministic blockers; invalid input or filesystem errors exit with code **1**. Review suggestions do not block basic chat.

`runtime_ready: true` means known configuration dependencies are bound. It does not establish model access, API availability, behavioral parity, or production readiness.

### Build a standalone app

```sh
python3 -m gptapps build migrated/apps/APP_ID.json --out dist/my-app
```

Replace `APP_ID` with the actual manifest filename. For a chat-created app, use its path under `apps/` instead. The output directory must be new. Then follow [Run a generated application](#run-a-generated-application). The same launchers are included in ZIP downloads from the builder.

### Use the plugin scaffold

[plugin/](plugin/) contains an optional migration skill and plugin manifest for a compatible host. It orchestrates collection, import, review, and generation using this framework. It is not installed or published by the repository and does not provide a hosted MCP server or private ChatGPT API scraper. Browser-assisted collection depends on the host's separate browser tools and signed-in session.

## Run a generated application

**Agents exports:** use the same launch commands below. `start.sh` automatically installs the pinned SDK in `.venv-agents`; Docker installs the export’s `requirements.txt` in its Python image. For manual startup, create a virtual environment and install `requirements.txt` first. Agents needs an explicit model and compatible project permissions; it does not use the Auto router. See the [standalone examples](docs/managed-workshop.md#standalone-applications).

Each generated folder or ZIP includes its own source code, README, Python launcher, and Docker launcher. You can move the entire folder to another computer; it does not need this framework checkout or access to the GPT in ChatGPT. The generated launchers start the **end-user app**, with builder controls and setup interpretation disabled.

### 1. Get the complete application folder

**From the browser:** select your app and click **Download standalone app**. Extract the complete ZIP into a new folder. For example, replace `APP_ID-app.zip` below with your actual download filename:

```sh
python3 -m zipfile -e "$HOME/Downloads/APP_ID-app.zip" "$HOME/my-gpt-app"
cd "$HOME/my-gpt-app"
```

You can also use your operating system's ZIP extraction tool; this is useful if you will use Docker and do not have host Python installed. A configuration-only JSON download is not a complete application bundle.

**From a CLI build:** open the output folder you chose:

```sh
cd dist/my-app
```

Make sure this folder contains `app.json` and the launch scripts:

```text
my-app/
├── app.json
├── compatibility.json
├── LICENSE
├── gptapps/             # Copied backend and web UI
├── run.py
├── start.sh             # Local Python launcher
├── docker-start.sh      # Docker launcher; no host Python needed
├── Dockerfile
├── scripts/             # Launcher helpers and container entrypoint
├── README.md
├── .gitignore
└── .dockerignore
```

### 2. Choose how to start it

**With local Python 3.11+:**

```sh
./start.sh
```

**With Docker Desktop or Docker Engine running:**

```sh
./docker-start.sh
```

The generated Dockerfile includes Python 3.13, so Docker users do not need host Python. If executable permissions were lost while extracting the ZIP, use `bash start.sh` or `bash docker-start.sh`.

Both scripts prompt for a missing OpenAI API key in the terminal with hidden input. For a fixed app, if neither the manifest nor your environment specifies an app model, they also ask for an API model ID, such as `gpt-6.1-sol`. Auto apps use their embedded policy and do not ask for an answer-model setting. They wait for readiness and open [http://127.0.0.1:8765](http://127.0.0.1:8765). Keep the terminal open and press **Ctrl+C** to stop the app or container.

For a fixed app, select the environment default model before launching:

```sh
export OPENAI_MODEL="gpt-6.1-sol"
./start.sh
# Or: ./docker-start.sh
```

The scripts reuse an already exported `OPENAI_API_KEY`. They keep a key entered at the prompt only for the current run. For fixed apps, `runtime.model` in `app.json` takes precedence over `OPENAI_MODEL`; set it to `null` with no `runtime.routing` if you want the environment default. Auto apps keep `runtime.model: null` and use the policy snapshot in `runtime.routing`; the original policy file and `OPENAI_MODEL` are unnecessary. Generated apps do not need `OPENAI_SETUP_MODEL`. Your API project must support the configured models and tools. No `.env` file is loaded automatically.

### 3. Use a different port or data folder

If the framework is still running on port 8765, start the generated app on another port:

```sh
./start.sh --port 9000
# Or: ./docker-start.sh --port 9000
```

The launcher opens [http://127.0.0.1:9000](http://127.0.0.1:9000) in this example. Other options work with either generated launcher:

```sh
./start.sh --port 9000 --data ./my-chat-history --no-browser
./docker-start.sh --port 9000 --data ./my-chat-history --no-browser
./start.sh --help
```

Relative data paths resolve from the generated app folder. By default, conversations and images are stored in that folder's `.gptapps-data/`. Docker mounts the host data folder so it survives container restarts; it mounts `app.json` read-only at runtime instead of copying private instructions into the image.

### Manual Python and Windows examples

If your key and app model are already configured in the terminal environment, run these commands from the generated folder:

```sh
python3 -m gptapps check app.json
python3 run.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) manually. A custom-port alternative is:

```sh
python3 -m gptapps serve --apps app.json --data .gptapps-data --port 9000
```

On Windows PowerShell, extract the ZIP and use Python 3.11+ directly. Replace the ZIP filename as needed:

```powershell
Expand-Archive -LiteralPath "$HOME\Downloads\APP_ID-app.zip" -DestinationPath "$HOME\my-gpt-app"
Set-Location "$HOME\my-gpt-app"
$apiKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $apiKey).Password
$env:OPENAI_MODEL = "gpt-6.1-sol"
py -3 -m gptapps check app.json
py -3 run.py
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765). The Python entrypoint needs no Bash or third-party Python packages. The `.sh` launchers require a Bash-capable environment.

### Compatibility, stopping, and sharing

Review `compatibility.json` or run the check command before relying on an app. Builds can contain unresolved requirements: real knowledge files need vector store bindings, and real Actions need backend adapters. Empty knowledge/Action lists are valid. A successful check does not certify live model access.

Press Ctrl+C before closing the launcher terminal. Keep `.gptapps-data/` to preserve conversations; stop the app and delete that directory only when you want to clear its local history and images. After changing `app.json`, its routing policy or a fixed app's effective model, restart the server and start a new conversation. Per-turn model selection under an unchanged Auto policy does not require a new conversation.

Generated apps contain your private GPT instructions. Their `.gitignore` excludes `app.json` and `compatibility.json` as well as keys and runtime data; deliberately review any configuration you choose to publish. Their configuration and content are not automatically made public or relicensed by building them. The included MIT license covers the copied framework source.

Rebuild or re-download apps created before these launchers were added to receive the new scripts and bundled instructions.

## Architecture

### Framework: migration, knowledge ingestion, routing, and build

```mermaid
flowchart TD
    Owner[Owner-provided GPT configuration] --> Chat[Web setup chat]
    Owner --> Export[Supported JSON export]
    Context[Chat picker or dropped files] --> ChatFiles[Validate current-step attachment context]
    ChatFiles --> Chat
    Chat --> Interpreter[Server-side AI interpreter<br/>Responses API + Structured Outputs]
    Interpreter --> Validation[Type and configuration validation]
    Chat --> Verbatim[Verbatim instructions / direct Action JSON]
    Verbatim --> Validation
    Export --> Importer[Export normalizer]
    Importer --> Spec[Versioned application manifest]
    Validation --> Review[User reviews interpreted configuration]
    Policy[Bundled routing-policy.json or operator override] --> PolicyCheck[Validate candidates, capabilities and limits]
    PolicyCheck --> Auto[Owner selects Auto: embed policy snapshot]
    Auto --> Review
    Chat --> Fixed[Owner selects fixed model / server default]
    Fixed --> Review
    Documents[Owner-selected local documents] --> Picker[Multiple-file picker]
    Picker --> Uploader[Builder server validates and forwards files]
    Uploader --> FilesAPI[OpenAI Files API<br/>POST /files]
    FilesAPI --> FileIDs[Uploaded file IDs]
    FileIDs --> Indexer[OpenAI Vector Stores API<br/>Create store and file batch]
    Indexer --> Poll[Builder polls file batch status]
    Poll --> Ready{Every file indexed?}
    Ready -->|Still indexing| Poll
    Ready -->|Failed or cancelled| Failure[Show error; do not change app binding]
    Ready -->|Ready| Binding[Validated vector store ID and filenames]
    Binding --> Review
    Binding --> Spec
    Uploader --> Metadata[(Local upload metadata and provider IDs<br/>No document bytes)]
    Poll --> Metadata
    Review --> Spec
    Spec --> RuntimeChoice{Explicit runtime}
    RuntimeChoice -->|Responses| Studio[Studio app chat: Responses runtime]
    RuntimeChoice -->|Agents fixed model| Managed[Durable managed run supervisor]
    Managed --> Sessions[Agents API sessions and hosted workspace]
    Sessions --> ManagedStatus[Task timeline, artifacts and execution receipt]
    Managed --> Ledger[(SQLite intents, events and tool results)]
    Spec --> Quality[Private behavioral comparison and human review]
    Quality --> Release[Release hold until current evaluation passes]
    Studio --> Evidence[Auto: bounded text and attachment metadata]
    Evidence --> Filter[Policy capability/context/output filter]
    Filter -->|Several eligible| Decisions[Decisions API: effort and task choices]
    Filter -->|One eligible| Select
    Decisions --> Select[Eligible tier and cost-rank selection / explicit fallback]
    Studio -->|Fixed| Answer[Responses API: stream full inputs and tools]
    Select --> ExplainWhen{Normal classification?}
    ExplainWhen -->|Yes| Explain[Responses API: bounded request assessment<br/>No tools; cannot change selection]
    Explain -->|Assessment or unavailable status| Answer
    ExplainWhen -->|Sole candidate or fallback| Answer
    Answer --> Status[Sidebar routing status and local history<br/>Answer model, reason and usage]
    Spec --> Report[Compatibility analysis]
    Spec --> Package[Standalone folder / ZIP]
    Report --> Package
    Release --> Package
    Package --> Dependencies[Runtime-specific requirements and local/Docker launchers]
```

The AI interpreter has no file-system, Action, or execution tools; explicitly attached documents are available as input content. It returns a proposed value for the current step or a clarification/navigation intent. The separate uploader forwards explicitly selected files using the server's API key, creates a vector store and batch, and checks indexing status. **Use these files** attaches only a ready collection to the reviewed draft; **Use files for this app** updates an existing app's knowledge binding. An indexing failure leaves an existing binding unchanged.

Framework launchers load the bundled starter policy automatically unless overridden; the owner still chooses Auto or Fixed during setup. Auto embeds only a validated nonsecret policy snapshot. The setup interpreter is never recursively routed; Studio and exports use the same explicitly selected runtime adapter. Fixed mode bypasses Decisions and request-assessment generation. The full chat input reaches the answering model after selection; the bounded evidence pass is separate.

Server validation runs before accepting settings; the final user instruction triggers app creation. Setup interpretation does not persist its own server conversation. Upload metadata persists locally for recovery, while document contents and the indexed vector store live in the OpenAI project. The ZIP includes the vector store ID and filenames, with no source documents, per-file upload metadata, upload-state files, or local conversation database. Packaging uses a runtime-file allowlist even if a custom data directory is nested under the source package.

### Generated app: routing, chat, and knowledge retrieval

```mermaid
flowchart TD
    Browser[App chat UI: text, picker, drag/drop] --> HTTP[Local Python HTTP server]
    HTTP --> Runtime[Validate inputs and load retained conversation]
    Manifest[(app.json: instructions, tools, bindings<br/>Fixed model OR embedded Auto policy)] --> Runtime
    Environment[Server environment: OpenAI API key] --> Runtime
    Runtime <--> SQLite[(Local SQLite conversations, attachments<br/>and compact routing records)]
    Runtime --> Adapter{Explicit runtime}
    Adapter -->|Responses| Mode{Model policy}
    Adapter -->|Agents fixed model| Supervisor[Durable supervisor and submission dedup]
    Supervisor <--> Runs[(Managed SQLite runs, events and tool results)]
    Supervisor <--> Agents[OpenAI Agents API sessions and turns]
    Agents <--> Sandbox[Hosted workspace: network disabled]
    Agents --> Function[Approved replay-safe read tools]
    Function --> Search[App-bound Vector Stores Search]
    Search <--> Knowledge
    Agents --> Artifacts[Completed-turn artifacts]
    Artifacts --> SafeFiles[Validate ownership, path, type and size]
    SafeFiles --> Downloads[(Private local artifacts)]
    Supervisor --> ManagedUI[Task timeline, receipts, reattach and downloads]
    ManagedUI --> HTTP
    Mode -->|Fixed| Pin[Pin one answer model for this turn<br/>including function-call rounds]
    Mode -->|Auto| Evidence[Bounded text/excerpts and file metadata<br/>PDF/Office/image contents excluded]
    Evidence --> Filter[Policy input/tool/context/output filter]
    Filter -->|Several eligible| Decisions[OpenAI Decisions API<br/>Effort and task typed choices]
    Filter -->|One eligible: skip classifier| Select[Choose approved candidate<br/>or compatible explicit fallback]
    Decisions --> Select
    Select --> ExplainWhen{Normal classification?}
    ExplainWhen -->|Yes| Explain[Responses API: brief request assessment<br/>Bounded text/metadata; no tools]
    Explain -->|Assessment or unavailable status| Pin
    ExplainWhen -->|Sole candidate or fallback| Pin
    Pin -->|Full original inputs and retained files| Responses[OpenAI Responses API: stream answer]
    Responses -->|If knowledge is bound| FileSearch[Hosted file_search]
    FileSearch <--> Knowledge[(OpenAI vector store<br/>Prepared by the framework)]
    FileSearch --> Responses
    Responses --> Hosted[Other enabled hosted tools]
    Responses --> Calls[Function call requests]
    Calls --> Registry[Approved read-only Python handlers]
    Registry -->|Same pinned model| Responses
    Responses --> Results[Text, citations, images and reported model/usage]
    Results --> Runtime
    Runtime --> Assets[(Local generated images)]
    Runtime --> Status[Sidebar below Recent Conversations<br/>Routing status: model, reason, fallback<br/>Separate classifier/explanation/answer usage]
    Status --> HTTP
    HTTP --> Browser
```

Each saved conversation is bound to its app ID and a configuration fingerprint: fixed apps include the effective model; Auto apps include the policy snapshot rather than the model chosen per turn. A changed app/policy or fixed model requires a new conversation, while unchanged Auto policies can select different models across turns. Previous user and assistant text, plus saved chat attachments, are replayed to the API with `store: false`. Chat attachment bytes remain in local private SQLite history; session UI responses expose names, MIME types and sizes only.

The generated app is self-contained: it reads the saved manifest and does not need the framework running or, for Auto, the original policy file. Its bundled router classifies bounded evidence through Decisions; original files go to the answering Responses request. The optional prompt-specific assessment and authoritative selection/fallback reasons remain visible in Routing status and saved history. When knowledge is bound, its Responses request declares `file_search` with `bindings.vector_store_ids`. OpenAI handles retrieval from the already indexed documents and returns answer text and file citations. Chat attachments go directly in the Responses request without creating hosted Files resources. Standalone apps do not upload permanent knowledge documents, create vector stores or run the setup interpreter. An explicitly selected Agents app instead uses managed sessions, a workspace file intake path and an app-scoped Vector Stores Search bridge; it does not reuse the Responses hosted-tool payload. Managed runs/events/artifacts have their own private storage and retention. See [the lifecycle guide](docs/managed-workshop.md). Use an API key with access to the same OpenAI project that owns the store; copying the ZIP to another machine does not copy or transfer the hosted knowledge.

## Attach files to chat

In both the public framework and every newly generated app, click **Attach files** next to the message box or **drag files into the chat**. Review the filename/size chips, remove anything you do not want to send, add a question, then click Send. Sending files without typed text is supported. Files stay in your browser until Send; failed requests keep the draft and files ready to retry. Switching conversations/apps or starting a new conversation clears unsent files.

- **Limits:** 5 files per message, 10 MiB per file, 20 MiB combined per message and conversation. Start a new conversation after reaching the cumulative limit. Invalid, empty or unsupported files are rejected before a model call.
- **Formats:** PDF; Word (`.doc`, `.docx`, `.rtf`, `.odt`); PowerPoint; Excel; text, Markdown, JSON, CSV, TSV, XML, HTML and supported source code; PNG, JPEG and WebP images. Archives, audio, video and executable binaries are unsupported. The file picker lists the accepted extensions.
- **Model access:** the configured model must accept the selected input types. PDF/image processing requires a vision-capable model. Non-PDF documents pass extracted text; embedded images/charts are not included. Spreadsheet processing may summarize/sample rows rather than include an entire workbook. See [OpenAI file-input documentation](https://developers.openai.com/api/docs/guides/file-inputs).
- **Data and cost:** the backend sends your typed text and inline `input_file` / `input_image` parts together to `POST /v1/responses`. This path creates no hosted File, vector store, or permanent knowledge binding. Accepted attachments are stored in private local SQLite conversation history for follow-ups and resent on each turn, increasing context usage and API cost. History is not encrypted at rest. Keep the data folder private. Display/history endpoints expose attachment metadata, never base64 bytes; app exports exclude conversation data.
- **Conversational setup:** attach documents as context for the current setup question. Clarification keeps the selected files queued for your next answer; advancing clears them. For the Instructions step, attach UTF-8 text/Markdown/code so its text can be preserved exactly, alongside any typed instructions. PDF/Word/image instructions must first be exported to text or pasted; the framework does not silently rewrite those instructions with AI. For Actions, attach an actual JSON array of complete definitions. The permanent-knowledge step uses its dedicated file picker/index controls, so chat attachments are disabled there. Review/creation requires an explicit typed confirmation without attachments. Attachments at a setup step do not automatically fill other steps.
- **Permanent knowledge:** use the separate **Knowledge files** upload/index panel when every user of the created app needs a searchable knowledge collection. Attaching a file to chat does not index it or bind it to the generated app.

Both chat paths use the server's existing `OPENAI_API_KEY`: regular chat uses a fixed app model/default `OPENAI_MODEL` or its embedded Auto policy; AI setup uses `OPENAI_SETUP_MODEL` (falling back to `OPENAI_MODEL`). Auto's separate bounded routing pass is described under [Attachment evidence, status and cost](#attachment-evidence-status-and-cost). No additional API credentials are needed. Existing downloaded apps need a **fresh standalone export** to receive the new UI and runtime.

Version **0.1.1** adds this feature to the public framework. The bottom-left label shows the installed version and build number. Source runs use a stable numeric source fingerprint; each standalone build receives a new immutable build number. Restarting an exported build retains its number. Release versions are maintained in `gptapps/version.py`.

## OpenAI APIs and tools

Responses chat answers/tools and setup inference use **`POST https://api.openai.com/v1/responses`**. Optional Auto classification uses **`POST https://api.openai.com/v1/decisions`**; fixed apps and sole-eligible-candidate routes skip that call. The framework's knowledge uploader also calls the Files and Vector Stores APIs listed below. All OpenAI calls run on the server; there is no OpenAI credential in browser requests.

| Caller / feature | API or tool | When used |
| --- | --- | --- |
| Framework: setup interpretation | Responses API with `text.format.type: json_schema`, `strict: true` | Natural-language setup replies and review/navigation intents |
| Framework: knowledge upload | Files API `POST /v1/files`, multipart upload with `purpose: assistants` | Once for each selected knowledge document |
| Framework: knowledge collection | Vector Stores API `POST /v1/vector_stores` | Creates a new collection for selected files |
| Framework: knowledge indexing | Vector Stores API `POST /v1/vector_stores/{id}/file_batches` | Indexes the uploaded file IDs together |
| Framework: indexing progress | Vector Stores API `GET /v1/vector_stores/{id}/file_batches/{batch_id}` | Checks completion and failed/cancelled counts before binding |
| Framework and converted app: Auto routing | Decisions API `POST /v1/decisions`, two typed choices using `gpt-6-luna` | Once before an Auto answer when multiple candidates are eligible; bounded text/metadata evidence only |
| Framework and converted app: routing explanation | Responses API `POST /v1/responses` with Structured Outputs, `gpt-6-luna`, `store: false` and no tools | Once after a normal Auto classification; generates a brief public request assessment from the same bounded evidence, with separate usage; never changes selection |
| Converted Responses app: chat | Responses API, with `stream: true` for the web chat | Each app conversation turn, using the fixed or selected answer model |
| Framework and converted app: chat attachments | Responses inline `input_file` and `input_image` content | Explicitly selected/dropped files sent with a message; no Files/Vector Stores call |
| Converted app: structured output | Responses `text.format` with the configured object JSON Schema | If `runtime.output_schema` is set |
| Converted app: web search | Responses hosted `web_search` tool | If enabled in `runtime.hosted_tools` |
| Converted app: image generation | Responses hosted `image_generation` tool | If enabled; returned images are saved locally |
| Converted app: code execution/data analysis | Responses hosted `code_interpreter` with an automatic container | If enabled |
| Converted app: knowledge retrieval | Responses hosted `file_search` | If existing `bindings.vector_store_ids` are configured |
| Converted app: backend integrations | Responses function calling plus local registered Python handlers | If explicitly bound to reviewed read-only tools |

| Agents app / Studio chat | Agents API session create/retrieve/delete, event stream/input events, turn/item retrieval | Managed runtime only; session identity persists across turns |
| Agents input files | Inline `environment.files` or Files API `purpose=user_data`, then environment Files API for follow-ups | Explicit chat attachments staged in the hosted workspace |
| Agents knowledge | Vector Stores `retrieve`, file inventory and `POST /v1/vector_stores/{id}/search` | Only stores bound to the app; reviewed `search_knowledge` function |
| Agents deliverables | Session Artifacts list/content | Completed-turn outputs, downloaded and validated by the server |
| Agents cleanup | Session delete and Files delete | Owned runtime resources only; shared knowledge retained |

Responses requests use `store: false`. Agents sessions have separate provider-managed persistence; that setting does not apply to them. This controls API response storage; it is not a guarantee about every aspect of provider data handling. Uploaded files and vector stores remain in your API project until removed or expired under OpenAI's policies; `store: false` does not delete them. See OpenAI's documentation and your project's policies.

**Not implemented:** direct Embeddings API calls, separate Images API endpoints, the separate Agents SDK orchestration loop, remote MCP connections, Realtime, transcription, speech synthesis, and moderation integrations. Hosted image generation and file search run through Responses. Original GPT Actions do not automatically become executable integrations. The Files API's `assistants` purpose is a file-use label; this framework does not call the Assistants API.

Adding knowledge files or Actions does not switch the generated app to Agents API. The owner explicitly selects the runtime. Responses uses hosted `file_search` and application-owned function rounds. Agents uses managed sessions plus the knowledge/function adapters described above. This is a general-purpose runtime choice, not a requirement for Custom GPT or Workspace-agent conversion. See the [Agents API quickstart](https://developers.openai.com/api/docs/guides/agents-api/quickstart) and [Studio implementation guide](docs/managed-workshop.md).

The separate [Workspace Agents API](https://learn.chatgpt.com/workspace-agents/trigger-runs)
triggers published agents that remain in ChatGPT. This framework does not implement
Workspace Agent import, Workspace API triggers, or automatic migration to Agents API.

Official references: [Decisions guide](https://developers.openai.com/api/docs/guides/decisions), [create decision](https://developers.openai.com/api/reference/python/resources/decisions/methods/create), [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [web search](https://developers.openai.com/api/docs/guides/tools-web-search), [image generation](https://developers.openai.com/api/docs/guides/tools-image-generation), [code interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter), [file search](https://developers.openai.com/api/docs/guides/tools-file-search), and [function calling](https://developers.openai.com/api/docs/guides/function-calling).

### Streaming and rich text

The web chat requests a live stream. The backend reads OpenAI's [Responses streaming events](https://developers.openai.com/api/docs/guides/streaming-responses) and flushes text deltas to the browser as they arrive. Tool activity updates the status while a request is working. Final text, citations, image attachments, and usage come from the terminal provider response. Completed turns are saved; usable text explicitly stopped by the output-token limit is saved with a partial-answer marker.

Assistant messages render Markdown headings, bold/italic text, lists, blockquotes, links, tables, and fenced/inline code. The same renderer is used during streaming and when reopening a saved conversation. User messages and setup instructions remain literal text. [Marked and DOMPurify](gptapps/vendor/README.md) are bundled with the source, generated apps, and Docker images; the UI does not depend on a CDN. Rendered markup is sanitized, external Markdown images are excluded, and scripts, event handlers, unsafe link schemes, and interactive forms are not allowed.

If OpenAI reports `incomplete_details.reason: max_output_tokens` with usable text, the answer remains visible and is saved with `message.incomplete_reason: max_output_tokens`. A notice identifies it as partial and offers **Continue response**. Clicking Continue sends one new follow-up in the same conversation; the app does not automatically retry, raise budgets, or continue in a loop. Saved conversations retain the notice. Incomplete structured JSON, function calls, reasoning-only responses, content-filter stops, and other failures are not accepted as usable text answers.

If a stream fails or ends without a terminal provider response, partial text is not saved. The UI restores the submitted input and displays the error. If a network interruption prevents confirmation, inspect saved conversations before resending. Previously generated apps need to be rebuilt or re-downloaded to include these changes; restart the server and refresh the browser after updating.

### Long responses and output limits (Responses runtime)

New app configurations default to **16,384 output tokens** per model call. This budget includes visible text and reasoning, so it is not a word count. You can edit `runtime.max_output_tokens` in the app manifest; the framework accepts budgets up to 131,072, but your selected model must support the value and sufficient context must remain. Higher limits permit greater API usage; actual usage is billed by OpenAI. See [OpenAI's reasoning and output-limit guidance](https://developers.openai.com/api/docs/guides/reasoning).

Existing configurations keep their explicit budget. Older manifests commonly use 2,048; downloading them again does not silently change that setting. For an existing app:

1. Rebuild or re-download it from the updated framework to receive the new runtime and interface.
2. Edit its `app.json` and change `runtime.max_output_tokens` to `16384` (or another supported budget). To make future downloads use that budget, edit the source manifest in the framework's app catalog as well.
3. Restart the server and start a new conversation after changing configuration.

If OpenAI uses the whole budget before producing visible text, the error now identifies `max_output_tokens`, the configured limit, and the need for reasoning headroom. No empty turn is saved. The older generic incomplete-response error did not retain the cause and cannot establish retrospectively which limit was hit.

## Application format

The canonical manifest uses schema version `1.0`:

| Section | Purpose |
| --- | --- |
| `id`, `name`, `description` | Safe application identity and display metadata |
| `instructions` | Full developer instructions, handled as configuration data |
| `conversation_starters` | Initial prompts shown in the app |
| `source` | Import/setup origin and source identifier |
| `runtime` | Responses API, fixed model or optional routing policy snapshot, hosted tools, limits, optional output schema |
| `bindings` | Vector store IDs, allowed function names, Action-to-function mappings |
| `requirements` | File inventory, Action IDs, unsupported enabled capabilities |
| `action_definitions` | Credential-free Action definitions for chat-created apps |

Frequently edited settings:

```json
{
  "runtime": {
    "api": "responses",
    "model": null,
    "routing": null,
    "hosted_tools": [],
    "max_output_tokens": 16384,
    "max_tool_rounds": 4,
    "output_schema": null
  },
  "bindings": {
    "vector_store_ids": [],
    "function_tools": [],
    "action_tools": {}
  },
  "requirements": {
    "knowledge_files": [],
    "actions": [],
    "unsupported_capabilities": []
  }
}
```

This is a fixed-mode manifest fragment; required identity and instruction fields are omitted for readability. For Auto, keep `model: null` and replace `routing: null` with the complete validated policy object, as shown in [the example policy](examples/routing-policy.example.json). Without routing, a null model uses `OPENAI_MODEL`. Existing manifests can be edited as JSON. Conversational editing of an already-saved app is not implemented. Restart its server and start a new conversation after changing configuration.

## Knowledge files and Actions

### GPTs without external resources

Empty knowledge and Action lists are valid. An app without knowledge files does not need `vector_store_ids`. An app without Actions does not need backend adapters. Natural-language absence replies are interpreted as empty lists; uncertainty triggers a follow-up.

### Knowledge retrieval

The builder can upload and index your documents directly in your OpenAI API project:

1. During **Create application**, reach the knowledge step. For an already saved/imported app, select it and open **Knowledge files** in the sidebar.
2. Choose multiple local documents, then click **Upload and index**. The UI shows selected filenames, upload progress, and indexing status.
3. Wait for **All files are indexed and ready**. Failed or partially indexed collections cannot be attached.
4. Choose **Use these files** during setup, then finish Actions and the final review. For an existing app, choose **Use files for this app**; this replaces its attached knowledge collection and starts a new chat. Previous OpenAI files/stores are retained.
5. Download the standalone app. Its `app.json` contains `bindings.vector_store_ids` and filenames. Use an API key from the same OpenAI project with access to those resources. The original document bytes, per-file provider metadata, and upload-state records are not included in the ZIP.

The browser sends one file at a time through the local framework server to OpenAI. The API key stays on the server, and the framework does not persist uploaded document contents locally. Owner-selected files become retrieval content; they are not interpreted as setup instructions.

**Framework upload limits:** up to 100 files per collection, 25 MiB per file, 100 MiB total; nonempty files with unique filenames. Supported formats are PDF, DOC/DOCX, PPTX, TXT, MD, JSON, and documented code formats (`.c`, `.cpp`, `.cs`, `.css`, `.go`, `.html`, `.java`, `.js`, `.php`, `.py`, `.rb`, `.sh`, `.tex`, `.ts`). Text should use UTF-8, UTF-16, or ASCII. These are this starter's upload limits, not the maximum limits of OpenAI's Files API. OpenAI may reject a file during indexing even if its extension and size are accepted. See [supported file-search formats](https://developers.openai.com/api/docs/guides/tools-file-search).

**Recovery and retention:** upload metadata and provider IDs persist under `.gptapps-data/knowledge-uploads/`. After a browser reload, open the panel and choose a collection under **Previously uploaded collections**. Ready files can be reused without uploading again. For an interrupted browser upload, reselect the same original files to resume; already uploaded bytes are checked locally without repeating the OpenAI upload. In-progress indexing can be checked again. A server interruption during a provider mutation is marked failed rather than retried automatically because its remote outcome may be uncertain.

Uploads and vector stores stay in your OpenAI project if setup is cancelled, indexing fails, a new collection replaces them, or you delete local framework data. OpenAI storage and retrieval charges may apply. The framework does not automatically delete remote resources; review the recorded file/store IDs and manage unused resources in your OpenAI project. It does not retry failed uploads automatically.

CLI/bulk imports still record a file inventory without transferring source files. You can use the builder's **Knowledge files** panel afterward, or set `bindings.vector_store_ids` to an existing indexed collection manually. Re-run `gptapps check` and test retrieval with representative questions.

An inventory with no vector store binding remains a blocker. Clearing real file requirements would change the app's intended behavior; only leave the inventory empty when the GPT has no such files.

### Actions

If there are Actions, paste a JSON array such as:

```json
[
  {
    "name": "Lookup",
    "auth_type": "none",
    "schema": {
      "openapi": "3.1.0",
      "info": {"title": "Lookup", "version": "1.0"},
      "paths": {}
    }
  }
]
```

This is a schema-only example, not a working endpoint. Supported `auth_type` values are `none`, `api_key`, and `oauth`; actual credentials do not belong in this JSON. The builder rejects obvious credential fields and token patterns, but inspect your configuration before sharing it.

The model cannot invent an executable Action from a description. For complete definitions, it asks for the original JSON, which the server preserves directly. Register a trusted backend function and map the recorded Action ID (for example, `action-1`) to that function in `bindings.action_tools`. Unbound Actions block execution. Automatic OpenAPI client generation, OAuth flows, and write operations are not implemented.

## Extensions

`gptapps.extensions.Registry` registers trusted `FunctionTool` implementations. Load only operator-supplied modules:

```sh
python3 -m gptapps serve --apps apps --builder \
  --extension my_extensions:register
```

Then add registered names to `bindings.function_tools` or `bindings.action_tools`. Handlers must validate their own arguments. Imported instructions and Action schemas are never loaded as Python modules.

The included `gptapps.extensions:scoring_example` registers `cosine_score` for supplied vectors. It does not create embeddings, score images, or implement a complete game. Domain rules, hidden state, exact scoring, source verification, and output invariants belong in explicit backend code. Write tools are blocked until an approval/idempotency adapter is implemented.

## Local HTTP interface

These routes are intended for the local UI, not an authenticated public service:

| Route | Purpose | Builder only |
| --- | --- | --- |
| `GET /` | Web chat UI | No |
| `GET /api/config` | UI mode, release/build, attachment limits and Auto policy availability/error | No |
| `GET /api/apps` | App summaries and compatibility reports | No |
| `POST /api/chat` | App chat turn; `stream: true` returns SSE, omitted/false returns JSON | No |
| `GET /static/chat.js`, `GET /static/vendor/...` | Bundled chat client and Markdown/sanitizer libraries | No |
| `GET /api/sessions?app=ID` | List saved conversations | No |
| `GET /api/sessions?app=ID&id=SESSION_ID` | Load an app's conversation | No |
| `GET /assets/FILENAME` | Generated image | No |
| `POST /api/setup` | Interpret `{field, message, history}` for the current setup step | Yes |
| `POST /api/apps` | Validate and save the reviewed draft | Yes |
| `POST /api/knowledge` | Start a validated collection from `{files: [{name, size}]}` | Yes |
| `POST /api/knowledge/file?id=UPLOAD_ID&index=N` | Forward one selected file as `application/octet-stream` | Yes |
| `POST /api/knowledge/index` | Index uploaded files with `{upload_id}` | Yes |
| `GET /api/knowledge` | List persisted upload collections for recovery/reuse | Yes |
| `GET /api/knowledge/status?id=UPLOAD_ID` | Refresh indexing status and counts | Yes |
| `POST /api/knowledge/bind` | Attach a ready collection with `{app_id, upload_id}` | Yes |
| `GET /api/spec?app=ID` | Download full configuration | Yes |
| `GET /api/build?app=ID` | Download a standalone ZIP | Yes |

JSON POST requests require `Content-Type: application/json`; the single-file upload route requires `application/octet-stream`. App creation can include `knowledge_upload_id` to attach an already indexed collection. Provider IDs supplied by the browser are not trusted as bindings; the server resolves them from its own validated upload record. Host/Origin checks reject unexpected local hosts and cross-origin browser requests. They are not user authentication.

For streaming requests, SSE data objects use `routing` (current selection or completed bounded routing metadata), `reset` (new answer/tool round), `delta` (text plus output/content indices), `status` (tool activity), `done` (saved session and final message), or `error`. The UI waits for `done` to confirm persistence. Successful assistant messages may contain optional `routing` metadata; legacy messages without it remain valid. A `routing` event alone does not confirm a saved turn. A `done` message carrying `incomplete_reason: max_output_tokens` is a saved partial answer, not a complete model response; API clients should display that distinction too. Validation errors before streaming starts return JSON with an error HTTP status; errors after streaming starts use an SSE `error` event.

## Privacy and public repositories

This project is a local, single-user starter. The source license does not imply that your exported GPT prompts, knowledge files, Action schemas, history, or generated app configurations are suitable for publication.

The root [.gitignore](.gitignore) excludes local secrets, `apps/`, `migrated/`, `exports/`, `knowledge/`, `.gptapps-data/`, generated archives, `dist/`, virtual environments, caches, and editor files. The public [example](examples/minimal-export.json) and tests contain generic fixture data. [.dockerignore](.dockerignore) restricts the image build context separately. Generated application folders have their own `.gitignore`.

Before your first public commit, inspect what will be staged. Ignore rules do not remove files that were already tracked and cannot detect private content saved under arbitrary names. Never commit `.env`, API keys, private exports, chat databases, or generated app ZIPs. Prefer the documented ignored directories for local data and generated builds.

Keys remain in the server environment. The framework does not log request bodies, authorization headers, or conversation text, and it summarizes provider errors. Instructions and relevant user inputs are sent to OpenAI when the associated API feature is used. Auto sends the documented bounded text/excerpts and attachment metadata to Decisions and, for a normal classification, to the Responses request-assessment call; full answering inputs then go to the answering Responses request. It adds no raw-evidence log or second stored copy of excerpts. The derived request assessment is saved with local chat history and may itself describe private task context. Local conversation history and generated images persist unencrypted under the data directory; stop the server and delete that directory to clear them. Failed requests can still incur API charges.

For shared hosting, add authentication, user-owned sessions, tenant isolation, HTTPS, secrets management, rate limits, budgets, backups/deletion policies, observability, and approved write handling. Docker packaging does not supply these controls.

## Limitations

- AI interpretation can make mistakes; the review step and server validation are still necessary.
- No behavior-parity guarantee, model-availability discovery, production hosting, accounts, or billing system.
- No private GPT scraping or automatic Action execution. Knowledge uploads/indexing require explicit file selection in the builder; standalone apps retrieve from the resulting store and do not expose upload controls.
- No full free-form, multi-field editor: AI interprets the current guided step and its clarification history.
- Responses streams do not resume after disconnect. Agents observers replay saved public events and reconcile provider work. User-message rich-text editing is not implemented.
- Auto routing does not extract binary documents/images, dynamically discover prices/access, grade answers, or automatically generate a second answer. Policy declarations and context estimates still require representative evaluation.
- Responses file citations display filenames; Agents knowledge citations link bounded retrieved passages. Source URL citations display links.
- Generated images are displayed, but image bytes and internal tool outputs are not replayed across turns; persistent image-editing workflows need an adapter.
- Responses Code Interpreter artifact downloads are not implemented; Agents hosted workspace artifacts use the validated download path.
- Current conversation limits are 80 stored messages (40 saved turns, including partial answers and continuations), 160,000 history/input characters, and 16,000 characters per user message.
- Voice, exact games/scoring, verified quotation workflows, and graph visualizations need domain extensions.

## Testing

Run the standard-library unit/integration suite:

```sh
python3 -m unittest discover -s tests -v
```

Tests use fake providers, temporary app catalogs, and isolated history. They cover import preservation, empty knowledge/Actions, multiple-file upload validation, multipart requests, indexing readiness/failures, upload recovery, provider redirect rejection, private export exclusion, configuration blockers, AI interpretation contracts, session isolation, function calling, standalone builds, and launchers. Routing coverage includes policy validation, bounded/metadata-only evidence, typed Decisions choices, capability filtering, fallback/error behavior, per-turn model pinning, fixed compatibility, history status, prompt-specific explanation validation/failures/usage, cancellation checkpoints and export policy snapshots. They do not require real keys or make OpenAI requests.

Streaming tests also verify that text arrives before provider completion, interrupted/disconnected turns are not committed, function-call rounds still work, and SSE parsing preserves UTF-8. Optional browser-stream decoder tests use Node's built-in test runner without npm dependencies:

```sh
node --test tests/test_chat_stream.js tests/test_knowledge_ui.js tests/test_chat_attachments.js tests/test_routing_ui.js tests/test_workshop_ui.js
```

To also build and test the real Docker image, start Docker and run:

```sh
GPTAPPS_TEST_DOCKER=1 python3 -m unittest discover -s tests -v
```

For optional local SDK launcher coverage, first create a disposable environment with `requirements-agents.txt`, then set `GPTAPPS_TEST_AGENTS_VENV` to its absolute path. The suite makes no OpenAI requests. With Docker enabled, it also builds Agents-enabled Studio and standalone images and verifies the pinned SDK/assets.

The Docker test checks the included Python version, custom-port startup, standalone packaging, and saved-app persistence across container restarts. It uses synthetic credentials and never calls OpenAI.

Optional real-browser smoke test:

```sh
python3 -m pip install playwright
python3 -m playwright install chromium
python3 tests/browser_smoke.py
```

The browser test uses the public example and a fake provider. It exercises live streaming, Markdown, safe HTML/links, saved-message rendering, sources, failure recovery, AI-assisted setup with clarifications, standalone downloads, mobile layout, and origin restrictions. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to use an existing Chromium binary. Screenshots are written to the ignored `preview/` folder.

Managed tests additionally cover submission deduplication, durable event tails, browser disconnect, process recovery, unknown outcomes, cancel/deadline races, knowledge scoping, replay-safe tools, artifact validation/cleanup, fixed-model setup and portable optional-SDK exports. Owner-reviewed comparison tooling is documented in [Evaluate before production](docs/managed-workshop.md#evaluate-before-production). A release check holds on unreviewed/stale evidence.

Before relying on a migration, also test representative tasks against a live API model in your own project. Mock tests do not establish semantic interpretation quality or access to every hosted tool.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Python is missing or older than 3.11 | Install a supported interpreter or use `./docker-start.sh` |
| Launcher cannot find the model/key in a non-interactive run | Set `OPENAI_API_KEY` and `OPENAI_MODEL` in that process's environment |
| `Set OPENAI_SETUP_MODEL or OPENAI_MODEL` | Configure a server model for AI-assisted setup; Auto answer routing does not configure setup |
| Auto is unavailable / missing routing policy | Update and restart `./start.sh` or `./docker-start.sh`; both load `routing-policy.json` by default. Restore a missing bundled file or choose another with `--routing-policy FILE`. For direct CLI use, pass `--routing-policy routing-policy.json`. Select Auto at creation |
| No eligible candidate / fallback ineligible | Review the embedded policy against all enabled inputs/tools, structured output and context/output budgets; do not remove requirements to force selection |
| Auto uses fallback | Expand Routing status for the actual uncertainty, invalid-decision or transient-service reason; verify candidate access and evaluate the policy |
| Decisions refusal, authentication or quota error | Resolve the displayed cause; these errors do not silently switch models or start an answer |
| Setup API error or timeout | Check access, billing, connectivity, and Structured Outputs support; retry the unchanged step |
| HTTP 429 with `credit_balance_exhausted` | Check prepaid API credits in the API key's organization and add credits if needed |
| HTTP 429 with `insufficient_quota` | Check API credits and usage/spend limits for the API key's organization/project; waiting alone will not restore quota |
| HTTP 429 with `organization_spend_limit_exceeded` or `project_spend_limit_exceeded` | Review the applicable spending limit, or wait for the monthly limit to reset |
| HTTP 429 with `organization_usage_limit_exceeded` | Request a higher approved organization usage limit or contact OpenAI support |
| HTTP 429 with `rate_limit_exceeded`, `rate_limit_error`, or `slow_down` | Follow the displayed wait time, reduce request frequency/concurrency, then retry |
| Setup asks about an uncertain reply | Answer the follow-up directly; uncertainty is not converted into an empty requirement |
| `knowledge_unbound` / “Upload/index the knowledge files” | Open Knowledge files in the builder, upload/index the documents and use the ready collection; correct the inventory to `[]` if the GPT has no files |
| `action_unbound` | Bind each recorded Action ID to a reviewed registered backend tool |
| `Application configuration changed` | Start a new conversation after changing the manifest, routing policy or fixed model |
| Port is unavailable | Stop your existing server/container or use `--port 9000` |
| Browser shows `Invalid host` | Use `http://127.0.0.1:PORT` or `http://localhost:PORT` with the configured port |
| Opening `gptapps/chat.html` directly fails | Use a launcher or `gptapps serve`; the UI needs the local backend |
| Docker cannot connect | Start Docker Desktop/the daemon and check Docker permissions |
| Docker bind-mount permissions fail | Use the launcher, which maps your host UID/GID, and choose writable host directories |
| Import/build destination already exists | Choose a new output directory; existing output is intentionally not overwritten |

### Understand OpenAI HTTP 429 errors

HTTP 429 alone does not identify the cause: OpenAI uses it for both temporary rate limits and credit/quota/spending limits. The client checks recognized provider error codes and displays a specific explanation while keeping arbitrary provider messages, request text, and credentials private. Specific billing codes take precedence over a broader `insufficient_quota` type. If no recognized code is available, the message keeps the cause explicitly uncertain. See OpenAI's [error code guide](https://developers.openai.com/api/docs/guides/error-codes).

For credit/quota errors, check [API billing](https://platform.openai.com/settings/organization/billing) and [API limits](https://platform.openai.com/settings/organization/limits) under the organization/project associated with the key you used. ChatGPT subscription billing is separate from API billing. Trying again, switching models, or regenerating the app does not restore depleted credits or raise an enforced spend limit.

For a temporary rate limit, wait at least as long as the provider's retry guidance specifies and reduce request frequency or concurrency. Recognized rate-limit errors display a numeric `Retry-After` value when one is available. The framework does not automatically retry API calls; billing/quota errors require account action before another attempt. See OpenAI's [rate-limit guide](https://developers.openai.com/api/docs/guides/rate-limits).

Restart the server to load client changes. Previously generated applications contain their own runtime copy; rebuild or re-download them to receive improved diagnostics. The older generic “HTTP 429; check model access, tools, billing and limits” message did not retain the cause, so it cannot retrospectively establish whether that request hit a rate limit or exhausted quota.

## Project layout

```text
.
├── gptapps/
│   ├── spec.py                 # Import, normalize, validate, analyze
│   ├── setup.py                # AI-assisted setup interpretation
│   ├── knowledge.py            # Files/Vector Stores client and persistent upload state
│   ├── runtime.py              # Responses client and chat/session runtime
│   ├── routing.py              # Policy, bounded evidence and answer-model selection
│   ├── decisions.py            # Server-side Decisions API client
│   ├── explanations.py         # Bounded public request assessments via Responses
│   ├── web.py                  # Local HTTP server and builder endpoints
│   ├── chat.html               # Builder and end-user UI
│   ├── chat.js                 # Streaming chat client and sanitized Markdown
│   ├── knowledge.js            # Multiple-file picker, upload progress, and ready binding
│   ├── routing.js / routing.css # Routing status rendering and responsive styles
│   ├── chat.css                # Shared responsive workspace and chat design
│   ├── icons/                  # Bundled Lucide icons and their license
│   ├── vendor/                 # Bundled browser libraries and their licenses
│   ├── build.py                # Standalone application packaging
│   ├── templates/              # Bundled standalone launchers and Docker files
│   ├── extensions.py           # Trusted Python function registry
│   └── cli.py                  # import / check / build / serve
├── examples/minimal-export.json
├── routing-policy.json          # Default starter policy for framework launchers
├── examples/routing-policy.example.json
├── plugin/                     # Optional migration skill scaffold
├── scripts/                    # Shared launcher helpers and container entrypoint
├── tests/                      # Fake-provider tests and optional browser smoke test
├── start.sh                    # Local launcher
├── docker-start.sh             # Docker launcher
├── run.sh                      # Compatibility shortcut to start.sh
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
├── pyproject.toml
└── LICENSE
```

`apps/`, `.gptapps-data/`, `migrated/`, `dist/`, and browser screenshots are local outputs and are ignored by Git.

## Contributing

Bug reports and focused pull requests are welcome through your repository host. Include the relevant Python/OS version, input shape, expected behavior, actual behavior, and steps to reproduce. Use synthetic examples; remove private GPT instructions, credentials, personal data, and conversation history.

For changes:

1. Use Python 3.11+ and keep runtime dependencies minimal.
2. Add meaningful regression coverage for changed behavior.
3. Run the test suite; run the browser smoke test for UI changes when available.
4. Update documentation when configuration, API usage, limits, or behavior changes.
5. Keep deterministic blockers separate from heuristic review suggestions.
6. Never execute imported instructions or load extensions from untrusted configuration.
7. When adding runtime modules/assets, update the build allowlist, package data, Docker allowlists, and packaging checks. Private data directories must never be exported.

Report security issues privately through your repository host's private reporting channel if available; do not include active credentials or exploit-sensitive details in a public issue.

## License

The framework's own source is distributed under the [MIT License](LICENSE). Bundled [browser libraries](gptapps/vendor/README.md) and [Lucide icons](gptapps/icons/README.md) retain their own licenses, which are included in generated apps. OpenAI services and Docker base images remain subject to their own terms and licenses. Your GPT instructions, files, Action definitions, and generated content remain separate from the framework's source license.
