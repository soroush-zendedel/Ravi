# Ravi AI Architecture
## Architecture and Behavioral Specification

**Projects:** RaviOS and the standalone Ravi repository  
**Component:** Ravi CLI and Ravi AI (`ravi`)  
**Status:** Proposed architecture — ready for implementation planning  
**Ravi repository:** `https://github.com/soroush-zendedel/ravi`  
**Ravi development branch:** `develop/ravi-ai`  
**Ravi base branch:** `main`  
**RaviOS integration:** pins and ships a specific stable Ravi release  
**Initial inference engine:** Ollama  
**Initial runtime:** Docker Engine  
**Initial hardware target:** Generic x86_64, CPU-only baseline  
**Document language:** English

---

## 1. Purpose

Ravi AI provides a simple, consistent command-line interface for enabling and managing local Generative AI capabilities on RaviOS.

The user interacts with the `ravi` command. The implementation details—Docker containers, Ollama, model storage, API communication, and service lifecycle—are managed behind that interface.

The first release integrates Ollama as the initial inference engine. The architecture must not make the `ravi` command, its configuration format, or its model-management contract permanently dependent on Ollama. Future inference engines and supporting AI services may be added without redesigning the public command interface.

Ravi AI is an optional platform capability. It is not part of the minimum RaviOS boot or Docker Engine requirements.

### 1.1 Goals

- Provide an approachable command-line interface for local GenAI.
- Install and run Ollama as a Docker-managed service.
- Keep model data independent of the Ollama container and image lifecycle.
- Use Docker-managed persistent storage for models.
- Support importing existing Ollama model stores from external paths.
- Support importing standalone model files, such as GGUF, through an explicit import workflow.
- Provide an interactive chat experience through `ravi`.
- Keep the base operating system small and independent of AI runtime packages.
- Distribute Ravi CLI as a standalone, versioned project with independently published stable releases.
- Allow Ravi CLI to be updated independently of RaviOS and the inference engine.
- Support CPU-only x86_64 systems as the baseline.
- Allow future GPU and alternative inference-engine support without changing the core contract.
- Make service and storage state observable through `ravi status`.

### 1.2 Non-goals for the first release

The first release does not aim to:

- Include model weights in the RaviOS image.
- Install Python, Node.js, or another general-purpose runtime on the host solely for Ravi AI.
- Build a custom Ollama image without a demonstrated technical requirement.
- Provide a web UI, remote multi-user service, authentication system, or public network endpoint.
- Automatically download a large model during first-time installation.
- Automatically delete, relocate, or overwrite user model data.
- Provide a vector database, RAG stack, agent framework, or AI gateway.
- Guarantee GPU acceleration on every x86_64 machine.
- Make Ollama a mandatory RaviOS system service.

---

## 2. Architectural principles

### 2.1 The `ravi` command is the public interface

Users should not need to know Docker commands, container names, image tags, internal volume paths, or Ollama administration commands for routine operations.

The public interface is `ravi`. Docker and Ollama are implementation details.

### 2.2 Runtime independence

Ollama is the first supported backend, not the definition of Ravi AI.

The implementation should separate:
- Public CLI commands and output.
- Ravi AI configuration and state.
- Docker operations.
- Inference-engine operations.
- Model storage and import operations.
- Interactive chat.

Backend-specific logic belongs behind internal functions or modules.

### 2.3 Persistent data is independent of containers

Model data must survive:
- Container removal and recreation.
- Ollama image upgrades and downgrades, subject to compatibility.
- `ravi stop` and `ravi restart`.
- Ravi AI uninstall and reinstall.

The models volume must never be implicitly removed by a routine service-management command.

### 2.4 No silent fallback to RootFS

Ravi AI must not silently store model weights in the RaviOS RootFS.

The Docker Engine's configured data root and Docker Data availability are prerequisites. If Docker storage is unavailable or invalid, Ravi AI must fail clearly rather than create an alternate model directory in RootFS.

This follows the RaviOS Docker Data design: persistent application data belongs to Docker Data, not the operating-system root filesystem.

### 2.5 Safe, explicit, recoverable operations

Operations that can destroy or replace persistent data require explicit confirmation. Import operations must not modify the source directory. Failures must be reported with actionable messages and must not leave the service in an ambiguous state.

### 2.6 Minimal host dependencies

The host-side CLI should be implemented in POSIX Shell compatible with BusyBox `ash`, unless implementation testing demonstrates a concrete limitation.

The host must not acquire Python, Node.js, or another general-purpose language runtime solely to support Ravi AI.

---

## 3. High-level architecture

```text
RaviOS
|
+-- Linux kernel
+-- Docker Engine
+-- ravi CLI
    |
    +-- Core CLI and command dispatcher
    +-- Configuration and state handling
    +-- Docker management adapter
    +-- Model management
    +-- Chat client
    |
    +-- Docker-managed AI services
        |
        +-- Ollama container
        |   +-- Ollama API
        |   +-- Inference runtime
        |   +-- /models mount
        |
        +-- Future optional services
            +-- Alternative inference engines
            +-- Supporting AI services
```

The first release requires only one container: Ollama.

### 3.1 Host responsibilities

RaviOS provides:
- Linux kernel and required container features.
- Docker Engine and its storage backend.
- The `ravi` executable.
- Ravi AI configuration and runtime state directories.
- Network connectivity needed to pull the image and download models.

RaviOS does not contain model weights or the Ollama runtime in its RootFS.

### 3.2 Container responsibilities

The Ollama container provides:
- The Ollama inference runtime.
- The Ollama HTTP API.
- Model loading and inference.
- Access to the persistent models volume.

The container is replaceable. Its writable container layer is not a persistent location for models or user configuration.

---

## 4. Storage architecture

### 4.1 Canonical models volume

The initial Docker volume has the following identity:

| Property | Value |
|---|---|
| Docker volume name | `models` |
| Logical Ravi volume ID | `33333333-3333-3333-3333-333333333333` |
| Managed label | `com.ravios.managed=true` |
| Component label | `com.ravios.component=ai-models` |
| Identity label | `com.ravios.volume-id=33333333-3333-3333-3333-333333333333` |
| Container mount path | `/models` |
| Container environment | `OLLAMA_MODELS=/models` |

The repeated-3 identifier is a Ravi-defined logical identity stored in Docker volume labels. It is **not** a Docker-generated volume ID, a filesystem UUID, or a promise about Docker's internal identifier.

Docker remains responsible for the actual volume ID and physical mountpoint.

### 4.2 Volume creation and validation

During installation:

1. Check that Docker is available and its daemon is healthy.
2. Check that Docker's data root is backed by the expected persistent Docker Data storage.
3. Inspect whether a volume named `models` exists.
4. If it does not exist, create it with the Ravi labels.
5. If it exists, verify all required Ravi identity labels.
6. If it is a valid Ravi-managed volume, reuse it without formatting or clearing it.
7. If it exists but has missing or conflicting identity labels, stop and report a name collision. Do not adopt, relabel, or delete it automatically.

The volume must be created using Docker's volume API/CLI. Ravi must not manually create or edit Docker's internal volume directory.

### 4.3 Volume lifecycle

The following operations must preserve the models volume:

- `ravi stop`
- `ravi start`
- `ravi restart`
- `ravi engine update`
- `ravi update` (Ravi CLI self-update; does not touch the volume)
- `ravi uninstall` (default behavior)
- Container replacement or recreation

A separate destructive command may be introduced later, for example `ravi models purge`, but it must:
- Clearly state that model data will be permanently deleted.
- Require explicit confirmation.
- Verify the volume identity before deletion.
- Never be invoked as a side effect of uninstalling the service.

### 4.4 Container mount and environment

The Ollama container mounts the volume as:

```text
models:/models
```

The container receives:

```text
OLLAMA_MODELS=/models
```

The host-side CLI must not assume that the physical volume path is permanently:

```text
/var/lib/docker/volumes/models/_data
```

Instead, it must obtain the actual mountpoint from Docker volume inspection.

### 4.5 `RAVI_MODELS` and `OLLAMA_MODELS`

These variables have different scopes and meanings:

- `OLLAMA_MODELS` is an environment variable inside the Ollama container. Its value is `/models`.
- `RAVI_MODELS` is a host-side convenience variable representing the currently resolved host mountpoint of the validated Ravi models volume.

`RAVI_MODELS` must not be treated as a hard-coded path. The `ravi` command should resolve the volume mountpoint from Docker when needed.

The implementation may export `RAVI_MODELS` to child processes launched by `ravi`. It must not depend on a manually maintained global shell environment variable being present in every user's login session.

The authoritative persistent configuration belongs in `/etc/ravi/config`. Runtime-derived values may be exposed to child processes or written under `/run/ravi/` while the system is running.

### 4.6 Docker Data dependency

Ravi AI must respect RaviOS Docker Data management.

Before installing or starting Ollama, verify:
- Docker daemon is running.
- Docker Data is available and valid.
- Docker's data root is on the expected persistent storage.
- The models volume can be inspected and mounted.

If Docker Data is missing, invalid, or ambiguous, do not start Ollama and do not create a fallback model store under RootFS.

The error should explain that the user must resolve Docker Data first, using the RaviOS Docker Data management tool.

---

## 5. Container and image policy

### 5.1 Initial image

Use the official Ollama image for the first release:

```text
ollama/ollama
```

The implementation must use an explicit, configurable version tag. It must not silently track `latest` in production behavior.

The exact initial version must be selected and verified during implementation. Image architecture support and compatibility with the target Docker Engine must be tested.

### 5.2 No custom image initially

A custom RaviOS Ollama image is not required for the first release.

A custom image may be justified later if Ravi AI needs:
- Additional runtime components inside the container.
- A maintained custom entrypoint.
- A specific build-time configuration.
- Reproducible patches not supported by the upstream image.

Host-side management logic belongs in `ravi`, not in an unnecessarily customized inference image.

### 5.3 Container identity

Use a stable, Ravi-owned container name, for example:

```text
ravi-ollama
```

Apply labels that identify ownership and role:

```text
com.ravios.managed=true
com.ravios.component=ai
com.ravios.service=ollama
```

Before modifying or removing an existing container with the expected name, verify its labels. Do not remove an unrelated container merely because its name collides.

### 5.4 Network exposure

The Ollama API must not be exposed on all host interfaces by default.

For the initial local CLI workflow, bind the API to loopback only, for example:

```text
127.0.0.1:11434
```

The exact Docker port mapping and Ollama listen configuration must be tested together. Do not publish `11434` as `0.0.0.0:11434` by default.

Remote access, selected development networks, and authentication are future explicit configuration features, not defaults.

### 5.5 Restart behavior

The service should recover after a normal system reboot when Ravi AI has been enabled and Docker Data is valid.

Container restart policy must not undermine the Docker Data safety contract. If Docker Data validation is a prerequisite, startup ordering and the RaviOS Docker Data service must ensure Ollama cannot start against an unintended RootFS-backed Docker data root.

The implementation must test boot ordering rather than relying only on an assumed Docker restart policy.

---

## 6. Distribution, Releases and Self-Update

Ravi is a standalone, versioned project distributed independently from RaviOS. Its source code and stable releases are published in the dedicated repository:

```text
https://github.com/soroush-zendedel/ravi
```

RaviOS integrates Ravi by shipping a known, pinned stable release as a local bootstrap. The RaviOS build must never depend on a floating `latest` release: the exact version and verified artifact are selected at build time so that OS images remain reproducible.

### 6.1 Separate product and version lifecycles

Three independently managed components must remain distinct:

1. **Ravi CLI:** the `ravi` command, its configuration schema, chat client, model management, and orchestration logic.
2. **Inference engine:** initially Ollama, distributed as a versioned Docker image and managed by Ravi.
3. **RaviOS:** the Buildroot-based operating system, kernel, Docker Engine, and system integration.

Updating one component must not implicitly update the others.

- `ravi update` updates the Ravi CLI itself.
- `ravi engine update` updates the configured inference-engine image.
- `ravi models update NAME` updates a specific installed model; `ravi models pull NAME` downloads or pulls a model when it is not already installed.
- RaviOS updates remain the responsibility of the RaviOS build/release process.

### 6.2 Bootstrap release shipped by RaviOS

The RaviOS image includes a local Ravi bootstrap entry point and a bundled, working release payload. The bootstrap is the entry point; the bundled release payload is the offline fallback if GitHub cannot be reached.

The bootstrap must be able to install the bundled local release without contacting GitHub. Once the full Ravi CLI is installed, it must be usable without contacting GitHub. The installed CLI must be sufficient to:
- Display help and version information.
- Check whether Ravi AI is enabled.
- Start the Ravi AI first-run enablement flow.
- Manage an already configured local service.
- Enter chat when the engine and a model are available.
- Perform all supported offline operations.

The release check is part of installing the full Ravi CLI from the bootstrap. It is not a prerequisite for running the bootstrap itself: if the check or download fails, the bundled release payload is installed and used. After the CLI is installed, this bootstrap check is permanently bypassed during ordinary command execution.

### 6.3 First-run release check

RaviOS ships a small bootstrap entry point and a bundled Ravi release payload. On the first invocation, if the full Ravi CLI has not yet been installed, the bootstrap checks the standalone Ravi repository for the latest stable CLI release. If it cannot retrieve and verify a newer release, it installs the bundled release payload. This check is about installing the CLI, not about whether the Ravi AI engine/service is enabled.

The sequence is:

1. Start the locally shipped bootstrap release.
2. Determine whether a full Ravi CLI release is already installed.
3. If it is installed, execute it directly; do not contact GitHub.
4. If it is not installed, attempt to retrieve the latest stable release metadata.
5. Compare the available release with the bundled local release.
6. If a newer stable release is available, download and verify its artifact.
7. Install the verified release safely; if the remote check or verification fails, install the bundled release instead.
8. Hand off to the installed CLI. The CLI then checks whether Ravi AI is enabled and, if not, displays the first-time enablement prompt.

The release check must not block or prevent use of the local version. It must not force the user to connect to the Internet.

This automatic check is limited to the initial installation of the full Ravi CLI and is attempted only while no active CLI release is installed. Persist the successful CLI installation state outside Docker Data, for example under `/var/lib/ravi/`. If the network check fails, installing the bundled local release still completes CLI installation and prevents repeated automatic checks. Cancelling the later Ravi AI enablement prompt does not trigger another GitHub check.

Once the full CLI is installed, running plain `ravi` never checks GitHub: if Ravi AI is not enabled, it displays the enablement prompt; if Ravi AI is enabled, it enters the local chat experience.

### 6.4 Manual self-update

After the initial setup, checking for and installing a newer Ravi CLI release is an explicit user action:

```sh
ravi update
```

`ravi update` updates Ravi itself—not Ollama, Docker Engine, or model weights.

The command should:
- Check the latest stable release metadata.
- Report the current and available versions.
- Download only when an update is available.
- Verify the release artifact before installation.
- Preserve configuration, runtime state, and the models volume.
- Install atomically or use an equivalent recoverable replacement strategy.
- Retain the previous working release until the new release has passed basic validation.
- Support a clear failure/rollback path.

A check-only mode may be provided:

```sh
ravi update --check
```

No periodic background updater is required in the first release. There is no automatic update check during ordinary chat or routine CLI execution.

### 6.5 Release format and version policy

Use Semantic Versioning for Ravi releases. Publish stable releases separately from prereleases and development builds.

Each GitHub Release should provide:
- A versioned source/runtime archive suitable for RaviOS.
- A SHA-256 checksum file.
- A machine-readable release manifest containing at least version, supported architecture/platform, artifact name, and checksum.
- A release note describing user-visible changes, compatibility notes, and migration requirements.

The runtime artifact must be suitable for the minimal RaviOS environment and its BusyBox/POSIX shell constraints. Do not assume that a generic Linux binary or a host with Python, Node.js, Bash, or Git is available.

The updater must select stable releases only by default. Prereleases require an explicit future opt-in mechanism.

### 6.6 Verification and safe installation

Never download and immediately execute an unverified script or archive.

At minimum:
1. Validate the release version and supported target.
2. Download the artifact to a staging location.
3. Verify its SHA-256 checksum against release metadata.
4. Prefer cryptographic signature verification using a public verification key embedded in the RaviOS bootstrap, if the selected release pipeline supports it.
5. Validate archive paths and expected contents before extraction.
6. Install into a version-specific directory.
7. Switch the active version using an atomic pointer/symlink replacement or another filesystem-safe mechanism.
8. Retain the previous version for rollback.
9. Clean up incomplete staging data without touching user configuration or models.

The final installation paths must be compatible with the RaviOS filesystem layout and RootFS update model. Do not place model data or other large mutable state in the CLI release directory.

### 6.7 Offline behavior and limits

Ravi CLI must remain usable offline after it has been shipped in the RaviOS image.

If the first-run release check cannot reach GitHub:
- Use the locally shipped bootstrap release.
- Continue the local first-run flow.
- Do not repeatedly retry during the same invocation.
- Do not report the local version as unusable merely because a newer release could not be checked.

Offline availability of the CLI does not imply that every first-time engine installation or model download can complete offline. If the required Ollama image is not cached locally, or the requested model is not present/importable, explain the missing resource and offer the supported offline import path. Never claim an engine or model was installed when it was not.

### 6.8 Repository responsibilities

**Standalone Ravi repository**
- Owns the CLI source, tests, documentation, release workflow, versioning, and self-update implementation.
- Publishes stable, versioned release artifacts and checksums/manifests.
- Does not own the RaviOS kernel, Buildroot configuration, or Docker Engine package.

**RaviOS repository**
- Owns the operating system and its integration points.
- Pins a specific Ravi release for reproducible image builds.
- Ships that release as the local bootstrap.
- Updates the pinned release through a deliberate RaviOS change, not by resolving `latest` during every build.

This separation allows Ravi to evolve and be updated independently while keeping RaviOS builds reproducible.

---
## 7. Installation and first-run experience

### 7.1 First invocation

When the full Ravi CLI is not yet installed, the bootstrap first installs the latest verified stable release or falls back to the bundled local release. It then launches the installed CLI. If Ravi AI is not yet enabled, running the installed command:

```sh
ravi
```

must display an introduction and ask for confirmation.

Suggested wording:

```text
Welcome to RaviOS AI

GenAI is not enabled on this system.

Enabling GenAI will:
  - Install the Ollama container
  - Create or reuse the persistent Docker volume: models
  - Configure persistent model storage
  - Enable AI management through the ravi command

Model files are stored separately from the Ollama container
and are preserved when the container is updated or removed.

[1] Enable GenAI
[2] Cancel
```

No installation, image pull, volume creation, or model download may begin before the user confirms.

### 7.2 Installation sequence

After confirmation:

1. Validate that the system is RaviOS and the required tools are available.
2. Validate Docker CLI and daemon availability.
3. Validate Docker Data and Docker's data root.
4. Check architecture compatibility.
5. Load and validate `/etc/ravi/config` defaults.
6. Inspect or create the `models` volume.
7. Pull the configured Ollama image if it is not locally available.
8. Create the Ollama container with the required labels, mount, environment, network binding, and restart behavior.
9. Start the container.
10. Wait for the Ollama API to become healthy, with a bounded timeout.
11. Save installation state.
12. Display a success message and next steps.

Installation must be safe to retry. If a step fails, the next invocation should inspect actual Docker state and continue or explain the required recovery action. It must not blindly create duplicate resources.

### 7.3 No automatic model download

Enabling GenAI installs the engine, not a model.

If no model is installed, `ravi` should explain that the user must pull or import a model before chatting.

The first release may offer a small list of suggested models, but model selection and download must be an explicit user action.

---

## 8. Command-line interface contract

The command interface should be predictable, scriptable, and extensible.

### 8.1 Top-level commands

| Command | Contract |
|---|---|
| `ravi` | The bootstrap installs the full CLI once if needed (latest verified stable release, or bundled offline fallback). The installed CLI then prompts to enable Ravi AI if it is not enabled; otherwise it enters interactive chat. |
| `ravi install` | Install or repair the Ravi AI engine/service (not the Ravi CLI) after confirmation where needed. |
| `ravi start` | Start the managed Ollama service. |
| `ravi stop` | Stop the managed Ollama service without deleting data. |
| `ravi restart` | Restart the managed service. |
| `ravi status` | Show installation, Docker, container, API, model volume, and model status. |
| `ravi update` | Update the Ravi CLI itself to the latest stable release. This is an explicit, manual operation after first-run setup. |
| `ravi update --check` | Check whether a newer stable Ravi CLI release is available without installing it. |
| `ravi engine update` | Update the configured inference-engine image (Ollama in the first release) using a safe replacement workflow. |
| `ravi engine status` | Show the configured engine, image version, container, and API health. |
| `ravi uninstall` | Remove the managed service/container while preserving the models volume by default. |
| `ravi config` | Display effective configuration and supported configuration options. |
| `ravi help` | Display command help. |
| `ravi version` | Display Ravi CLI and configuration schema versions. |

### 8.2 Model commands

| Command | Contract |
|---|---|
| `ravi models list` | List models known to the running Ollama service. |
| `ravi models pull NAME` | Download/pull a model through the configured engine when it is not already available. |
| `ravi models update NAME` | Ask the configured engine to pull the specified model tag again, updating that model while preserving other models. |
| `ravi models import PATH` | Import a supported external model source. |
| `ravi models refresh` | Reconcile and report model-store state without deleting data. |
| `ravi get PATH` | Convenience alias for importing a valid external Ollama model store. |

`ravi get PATH` must not ambiguously mean both “download a model by name” and “copy a directory”. Downloading by model name belongs to `ravi models pull NAME`.

### 8.3 Engine commands

The first release exposes the inference engine through its own namespace, even though Ollama is the only backend:

| Command | Contract |
|---|---|
| `ravi engine status` | Report engine installation, configured image/version, container state, and API health. |
| `ravi engine update` | Pull and safely replace the configured engine image while preserving the models volume. |

This keeps engine lifecycle operations distinct from Ravi CLI self-updates. Future backends can be added without overloading the top-level `ravi update` command.

### 8.4 Future command namespace

The CLI should reserve room for future service namespaces:

```text
ravi service ...
ravi models ...
ravi config ...
```

Do not implement speculative commands until there is a real feature behind them.

### 8.5 Exit codes

Use stable non-zero exit codes for automation. At minimum distinguish:
- Invalid command or arguments.
- Ravi AI not installed.
- Docker unavailable.
- Docker Data unavailable or invalid.
- Volume identity conflict.
- Service not running or failed to become healthy.
- Model not found or unavailable.
- Import validation or copy failure.
- User cancellation.

Exact numeric values should be documented in the implementation reference and kept stable after release.

### 8.6 Output behavior

- Human-readable output is the default.
- Errors go to standard error.
- Success and status information go to standard output.
- Avoid printing secrets or environment values that may contain credentials.
- A future `--json` mode may be added for machine-readable status; it is not required for the first milestone.
- Long operations should show clear progress or a clear current step, without requiring an external progress framework.

---

## 9. Interactive chat contract

### 9.1 Entry behavior

When Ravi AI is installed and the service is available:

```sh
ravi
```

enters an interactive chat session.

The first assistant message must be:

```text
Hi!
```

This is a UI greeting, not a model-generated response. It must not trigger an inference request.

### 9.2 Chat implementation

The `ravi` chat client communicates with the Ollama HTTP API through the loopback endpoint.

It should:
- Ask Ollama for the available models.
- Use the configured default model if one is set.
- If no default model is configured and multiple models exist, ask the user to choose.
- If no model exists, show instructions for `ravi models pull` or `ravi models import`.
- Send user prompts to the selected model.
- Display responses in the terminal.
- Preserve conversation context during the current chat session.
- Exit cleanly on Ctrl+C or the documented exit command.

The initial implementation may keep conversation history in memory only. Persistent chat history is outside the first release unless explicitly added later.

### 9.3 API and streaming

The chat implementation should use Ollama's documented API and support streamed responses if this can be implemented reliably with the available host utilities.

Do not assume `curl`, Python, or `jq` exists on the base image. During implementation, inventory the available BusyBox applets and Buildroot packages. Select the smallest maintainable solution:
- BusyBox `wget` or another already available HTTP client if it can handle the API protocol and streaming requirements.
- A small dedicated native client if shell parsing becomes fragile.
- A minimal additional package only if justified.

Avoid writing a fragile JSON parser in shell. JSON escaping, Unicode, multiline prompts, and streamed response parsing must be tested.

### 9.4 Chat errors

The chat UI must distinguish:
- AI service not installed.
- Service stopped.
- Service starting or unhealthy.
- No model available.
- Selected model unavailable.
- API communication failure.
- Inference failure.

It should offer a useful next command, such as `ravi start` or `ravi models pull NAME`, rather than exposing raw Docker errors as the only feedback.

---

## 10. Model management and import behavior

### 10.1 Ollama model store

Ollama manages its model store and metadata. Ravi must treat the internal store layout as Ollama-owned data.

The expected store commonly contains structures such as:

```text
models/
  blobs/
  manifests/
```

Ravi must not invent, rewrite, or manually generate Ollama manifests as part of a normal import.

### 10.2 Importing an existing Ollama model store

`ravi get PATH` is intended for a directory that already contains a valid Ollama model store.

The import workflow must:
1. Validate the source path and expected store structure.
2. Confirm that the destination models volume is valid.
3. Ensure the Ollama service is stopped or use a verified safe synchronization procedure.
4. Copy data without modifying or deleting the source.
5. Preserve directory structure and required file contents.
6. Avoid overwriting existing blobs with different content.
7. Report copied, already-present, skipped, and failed items.
8. Validate the resulting store before restarting the service.
9. Restart the service only if it was running before the operation and the import completed successfully.

A failed import must not silently be reported as successful. The implementation should use a staging or recoverable copy strategy where practical.

### 10.3 Importing standalone GGUF files

A standalone `.gguf` file is not automatically a complete Ollama model store.

`ravi models import PATH` must use an Ollama-supported model creation workflow, such as generating a temporary `Modelfile` that references the imported GGUF file and invoking the supported Ollama model creation operation.

The exact workflow must be verified against the selected Ollama version.

The source file must remain untouched. Ravi should copy or stage the file into an appropriate managed location before creating the Ollama model, and clean up temporary files only after success.

The user must be told that importing a model file and copying an existing Ollama model store are different operations.

### 10.4 Refresh behavior

`ravi models refresh` is a non-destructive reconciliation operation.

It may:
- Check that the volume is mounted and accessible.
- Query Ollama for its known models.
- Detect whether external files have appeared in the store.
- Reconcile reported model information with the service.
- Report missing, unavailable, or inconsistent data.
- Refresh cached Ravi status information.

It must not:
- Delete unknown files.
- Delete models that Ollama does not currently list.
- Automatically rewrite manifests.
- Automatically overwrite model blobs.
- Treat a directory scan as proof that a model is valid.

If Ollama requires a service restart to recognize externally copied data, the command must explain this and perform it only under a clearly documented policy. The first implementation should prefer a controlled stop/copy/start import workflow rather than promising hot refresh behavior.

---

## 11. Configuration and state

### 11.1 Configuration location

Persistent Ravi AI configuration:

```text
/etc/ravi/config
```

The installed CLI release and bootstrap installation marker must live outside Docker Data. A suitable initial layout is:

```text
/usr/lib/ravi/releases/<version>/
/usr/lib/ravi/current -> releases/<version>/
/var/lib/ravi/cli-installed
```

The exact layout may change to fit the RaviOS filesystem and update model, but model data must never be stored here.

Runtime state:

```text
/run/ravi/
```

The runtime directory is volatile and may be recreated at boot.

### 11.2 Configuration values

The initial configuration should support at least:

| Setting | Purpose |
|---|---|
| `OLLAMA_IMAGE` | Explicit Ollama image and version tag |
| `OLLAMA_CONTAINER` | Managed container name |
| `OLLAMA_HOST_PORT` | Host loopback port for the API |
| `OLLAMA_DEFAULT_MODEL` | Default model for interactive chat |
| `OLLAMA_KEEP_ALIVE` | Optional model keep-alive policy, if exposed |
| `RAVI_CHAT_MODE` | Chat behavior/versioned setting if needed |

The models volume name and logical identity are system constants in the first release, not casually user-editable settings. Changing them requires a deliberate migration design.

Configuration parsing must be safe for a shell script. Do not blindly source a user-writable file as shell code unless permissions and format are tightly controlled. Prefer a simple validated key-value format with restricted characters and explicit parsing.

### 11.3 State versus configuration

Configuration describes desired behavior. Runtime state describes what Docker is actually running.

`ravi status` must inspect Docker and the API rather than trusting a stale “running” flag in a file.

If a state file is used, it is a cache or diagnostic record, not the source of truth for container or volume existence.

### 11.4 Permissions

- Configuration should be root-owned and not writable by unprivileged users.
- Docker management operations require the appropriate privilege.
- The first release may require root for installation and service management.
- The interactive chat command should not require more privilege than necessary once the service is installed and the loopback API is accessible.
- Do not add a complicated permission model in the first release.

---

## 12. Lifecycle and update behavior

### 12.1 Start

`ravi start` must:
1. Validate Docker and Docker Data.
2. Validate the models volume identity.
3. Verify that the managed container exists and has expected labels.
4. Start the container or create it if the documented repair behavior permits.
5. Wait for API readiness with a timeout.
6. Report success or a useful failure reason.

It must never start an unmanaged container just because its name matches.

### 12.2 Stop

`ravi stop` stops the managed container gracefully.

It must not:
- Remove the container.
- Remove the models volume.
- Delete models.
- Change Docker Data configuration.

### 12.3 Restart

`ravi restart` is equivalent to a controlled stop followed by start. If start fails, report that the service remains stopped and preserve all model data.

### 12.4 Engine update

`ravi engine update` updates the configured inference-engine image (Ollama in the first release) while preserving the models volume.

The engine update workflow should:
1. Check Docker Data and the models volume.
2. Pull the configured new image.
3. Record the currently running image/version for rollback diagnostics.
4. Stop the managed container.
5. Recreate it with the same stable configuration and volume mount.
6. Start it and verify API readiness.
7. Report the new version and retained model volume.
8. If the new container fails, provide a clear rollback procedure.

Do not delete the old image until the new container is healthy and rollback is no longer needed.

The exact policy for automatic rollback versus leaving the new container stopped must be selected during implementation. Model-store compatibility across Ollama versions must be considered; an image downgrade may not always be safe after a model-store migration.

### 12.5 Uninstall

Default behavior:

```sh
ravi uninstall
```

- Stop and remove only the Ravi-managed Ollama container.
- Preserve the `models` volume.
- Preserve user model data.
- Preserve unrelated Docker resources.
- Keep or remove configuration according to an explicit prompt and documented choice.

The command must clearly state that model data remains on disk and can be reused after reinstalling Ravi AI.

A future explicit purge operation may remove the models volume, but it is not part of ordinary uninstall.

---

## 13. Status contract

`ravi status` should report at least:

```text
Ravi AI

Installation:       Installed
Engine:             Ollama
Container:          ravi-ollama
Container status:   Running
API status:         Ready
Image:              ollama/ollama:<configured-version>

Docker Data:        Available
Models volume:      models
Volume identity:    Valid
Models location:    <resolved Docker mountpoint>
Container path:     /models
Model count:        <count>
Default model:      <name or Not configured>
```

Status must distinguish:
- Not installed.
- Installed but stopped.
- Starting.
- Running and API-ready.
- Running but API-unavailable.
- Docker unavailable.
- Docker Data unavailable or invalid.
- Models volume missing.
- Models volume identity conflict.
- Models volume inaccessible.

Do not print a guessed models path. Resolve the real Docker volume mountpoint and report it. If Docker cannot provide it, report that the path is unavailable.

---

## 14. Error handling and recovery

Every operation must fail safely and explain:
- What failed.
- Whether persistent model data is safe.
- Whether the service is currently running or stopped.
- What the user can do next.

Examples:

| Condition | Required behavior |
|---|---|
| Docker daemon unavailable | Stop; do not create local fallback storage. |
| Docker Data unavailable | Stop; explain how to resolve Docker Data. |
| `models` name collision | Stop; do not adopt or alter the volume. |
| Invalid Ravi volume identity | Stop; preserve the existing volume untouched. |
| Image pull failure | Preserve existing container and volume where possible. |
| Container startup timeout | Report logs/status guidance; preserve volume. |
| API unavailable | Do not claim the service is ready. |
| Model missing | Explain pull/import commands. |
| Import interrupted | Preserve source; report partial destination state and recovery action. |
| Update failure | Preserve model volume and provide rollback guidance. |
| Uninstall | Remove only verified Ravi-managed resources. |

Operations should be idempotent where practical: repeating a successful `install`, `start`, or `stop` should not create duplicate resources or damage existing state.

---

## 15. Security and networking baseline

The first release is intended for local developer use.

Baseline requirements:
- Bind Ollama's API to host loopback only.
- Do not publish the API on all interfaces by default.
- Do not mount the Docker socket inside the Ollama container.
- Do not run Docker management commands from inside the Ollama container.
- Do not expose the models volume to unrelated containers by default.
- Use a pinned image version rather than an unbounded `latest` tag.
- Validate Docker labels before managing or deleting resources.
- Keep host configuration root-owned.
- Do not log prompts or model responses by default.
- Do not add remote access or authentication features until there is an explicit requirement.

The `ravi` host process uses the Docker CLI/API available on the host. The Ollama container itself does not need Docker socket access.

---

## 16. Hardware and platform support

### 16.1 Initial baseline

- Architecture: x86_64.
- Inference: CPU-only.
- Docker Engine: required.
- Persistent Docker Data: required.
- RAM and disk capacity: model-dependent; display warnings where possible.

### 16.2 GPU support

GPU support is optional and outside the first milestone.

The architecture must avoid assumptions that a GPU is present. Future support may add runtime-specific configuration for supported NVIDIA, AMD, or Intel hardware, but must not make GPU drivers or toolkits mandatory in the base RaviOS image.

### 16.3 Resource configuration

Resource limits and Ollama runtime settings should be configurable in a later iteration. The first release should avoid arbitrary universal limits that would make the appliance unusable on larger machines or unstable on smaller ones.

---

## 17. Implementation structure

Proposed source layout:

```text
tools/
  ravi/
    ravi
    lib/
      common.sh
      config.sh
      docker.sh
      service.sh
      volume.sh
      models.sh
      chat.sh
    tests/
      ...
    README.md
```

The exact layout may be adjusted to match existing RaviOS conventions.

The installed host executable:

```text
/usr/bin/ravi
```

Persistent configuration:

```text
/etc/ravi/config
```

Runtime files:

```text
/run/ravi/
```

Buildroot integration should install only the required scripts and configuration defaults. The implementation must follow the project's existing rootfs overlay/package conventions rather than inventing a parallel installation mechanism.

### 17.1 Module responsibilities

- `common.sh`: logging, errors, exit codes, privilege checks, common utilities.
- `config.sh`: configuration defaults, validation, and loading.
- `docker.sh`: Docker availability, image, container, and volume inspection helpers.
- `service.sh`: install, start, stop, restart, update, uninstall, health checks.
- `volume.sh`: volume creation, labels, identity validation, mountpoint resolution.
- `models.sh`: list, pull, import, refresh, and model-store validation.
- `chat.sh`: API requests, model selection, conversation loop, and terminal output.
- `ravi`: argument parsing and command dispatch.

Keep functions small and testable. Avoid mixing user-facing output, Docker command construction, and model import logic in one large script.

---

## 18. Testing and acceptance criteria

Testing must include both host-side command tests and real VM runtime tests.

### 18.1 Installation

- First `ravi` invocation shows the enablement prompt.
- Cancel performs no changes.
- Confirm installs the configured Ollama image and creates or reuses the validated volume.
- Re-running installation does not create duplicate resources.
- Installation fails safely if Docker Data is unavailable.
- Installation refuses an unrelated `models` volume.

### 18.2 Persistence

- Pull a model and verify it is stored in the `models` volume.
- Stop and start the container; verify the model remains.
- Remove and recreate the container; verify the model remains.
- Update the Ravi CLI independently; verify configuration and models are preserved.
- Update the Ollama image through `ravi engine update`; verify the volume is reused.
- Update a named model through `ravi models update NAME`.
- Uninstall and reinstall; verify the model remains available.
- Verify no model data is written to RootFS as a fallback.

### 18.3 Model import

- Import a valid existing Ollama model store.
- Reject a directory that is not a valid Ollama model store.
- Import a standalone GGUF through the supported creation workflow.
- Verify source files are unchanged.
- Interrupt an import and verify the failure is reported accurately.
- Run refresh and verify it does not delete unknown or unlisted files.

### 18.4 Chat

- `ravi` displays `Hi!` as the initial assistant greeting.
- A configured default model is selected automatically.
- Multiple models without a default cause a clear selection prompt.
- No installed model produces helpful instructions.
- User prompts and model responses work with Unicode and multiline text.
- Streaming output works if included in the selected implementation.
- Ctrl+C exits cleanly.
- Service/API failures are clearly distinguished.

### 18.5 Lifecycle and safety

- `stop`, `start`, and `restart` preserve the volume.
- `status` reports actual Docker state and the actual volume mountpoint.
- `uninstall` removes only Ravi-managed resources.
- A container-name collision does not result in removal of an unrelated container.
- API port is bound to loopback only by default.
- The Ollama container has no Docker socket mount.
- Boot behavior is tested with Docker Data available and unavailable.

### 18.6 Reproducibility

- Buildroot image contains a pinned, locally usable Ravi bootstrap release and the required integration configuration.
- Buildroot does not resolve a floating `latest` Ravi release during image creation.
- No model weights are included in the generated RaviOS image.
- No unnecessary host language runtime is added.
- Tests are repeatable in the project's documented Docker/VirtualBox development environment.

---

## 19. Delivery milestones

### Milestone 0 — Architecture and repository preparation

- Approve this architecture.
- Create the standalone Ravi repository with an initial `main` branch.
- Add this architecture document and the initial repository overview to the new repository.
- Create `develop/ravi-ai` from the repository's `main` branch.
- Define the release artifact, manifest, checksum/signature policy, and versioning workflow.
- Define how RaviOS pins and packages a specific Ravi bootstrap release.
- Agree on image version, API client implementation, and configuration details.

### Milestone 1 — Core CLI and Docker integration

- Add `ravi` command dispatcher.
- Add configuration loading and validation.
- Add Docker and Docker Data preflight checks.
- Create and validate the persistent models volume.
- Install, start, stop, restart, and report Ollama service status.
- Implement safe uninstall that preserves models.

### Milestone 2 — Model management

- List and pull models.
- Import an existing Ollama model store.
- Import standalone GGUF files.
- Implement non-destructive refresh.
- Test persistence and interrupted operations.

### Milestone 3 — Interactive chat

- Implement the chat API client.
- Display the initial `Hi!` greeting.
- Add model selection and default-model handling.
- Support Unicode, multiline input, errors, and clean exit.
- Add streaming if the selected minimal implementation supports it reliably.

### Milestone 4 — Distribution, self-update, and reliability

- Publish a versioned Ravi release with manifest and checksums.
- Implement first-run release checking with local offline fallback.
- Implement manual `ravi update` for the Ravi CLI with verification and rollback.
- Implement `ravi engine update` for safe inference-engine image updates.
- Implement safe engine image update and recovery.
- Test reboot behavior and startup ordering.
- Complete acceptance tests on the target VM.
- Document user-facing commands and known limitations.
- Tag a Ravi AI milestone after review and tests.

---

## 20. Decisions to confirm before implementation

The following are intentionally left as implementation choices rather than silently assumed facts:

1. **Ollama image version:** choose and pin a version after checking upstream release and architecture support.
2. **Chat HTTP client:** determine whether existing BusyBox tools are sufficient or whether a small dedicated client is justified.
3. **Default model behavior:** decide whether the first installed model automatically becomes the default or whether the user must select one.
4. **Model import implementation:** verify the exact supported Ollama workflow for existing stores and standalone GGUF files.
5. **Update failure policy:** decide whether Ravi automatically rolls back to the previous image or leaves the service stopped with a manual rollback command.
6. **Configuration format:** settle on a strictly validated key-value format compatible with BusyBox `ash`.
7. **Service boot integration:** choose the exact Buildroot init script and dependency ordering so Docker Data validation precedes Ollama startup.
8. **Volume label schema:** freeze the label keys and logical ID before the first release.

These decisions should be resolved during implementation planning and recorded in this document or a short decision log.

---

## 21. Final architectural decisions

The following are the baseline commitments for the first implementation:

- `ravi` is the user-facing AI management command.
- Ravi AI is optional and is not part of the minimum RaviOS runtime.
- Ollama runs in a Docker container using an explicit versioned image.
- The first release targets CPU-only x86_64.
- The Docker volume is named `models`.
- The Ravi logical volume ID is `33333333-3333-3333-3333-333333333333`, stored as a Docker label.
- The container mountpoint is `/models`.
- `OLLAMA_MODELS=/models` is set inside the Ollama container.
- `RAVI_MODELS` represents the dynamically resolved host mountpoint; it is not a hard-coded Docker path.
- Docker Data is a hard prerequisite; no RootFS fallback is permitted.
- Model data survives container replacement, service uninstall, and image updates.
- Existing Ollama model stores and standalone GGUF files use distinct import workflows.
- `ravi` opens an interactive chat when AI is enabled and displays `Hi!` as its initial greeting.
- The first release does not automatically download a model.
- The Ollama API is loopback-only by default.
- The initial implementation uses the official Ollama image unless a concrete requirement justifies a custom image.
- Ravi is distributed from a standalone GitHub repository with stable, versioned releases.
- RaviOS ships a bootstrap entry point and a pinned local fallback release; builds never resolve a floating latest version.
- A latest-stable release check is attempted only when the full Ravi CLI is not yet installed; failure falls back to the bundled local release.
- Once the full CLI is installed, ordinary command execution and chat never contact GitHub. CLI updates are manual through `ravi update`.
- `ravi update` updates only Ravi CLI; `ravi engine update` updates the inference engine; `ravi models update NAME` updates the named model.

---

## Appendix A — Example user workflow

```sh
# First run: bootstrap installs the latest verified CLI release (or bundled offline fallback); then the CLI may prompt to enable Ravi AI
ravi

# Service lifecycle
ravi status
ravi start
ravi stop
ravi restart

# Model operations
ravi models list
ravi models pull llama3.2
ravi models import /mnt/models/custom-model.gguf
ravi get /mnt/backup/ollama-model-store
ravi models refresh

# Interactive chat
ravi

# Manually update Ravi CLI itself
ravi update

# Check for a Ravi CLI update without installing it
ravi update --check

# Update the Ollama runtime without deleting models
ravi engine update

# Update a specific installed model
ravi models update llama3.2

# Remove the service while preserving model data
ravi uninstall
```

## Appendix B — Important terminology

| Term | Meaning |
|---|---|
| Ravi AI | The optional AI capability and its management contract in RaviOS. |
| `ravi` | The host-side CLI used by the user, distributed independently from RaviOS. |
| Ollama | The initial inference engine, running in a container. |
| Models volume | The persistent Docker volume named `models`. |
| Logical volume ID | Ravi-defined identity stored in volume labels; not Docker's internal ID. |
| `OLLAMA_MODELS` | Container-side Ollama model directory setting. |
| `RAVI_MODELS` | Host-side runtime value for the resolved models volume mountpoint. |
| Docker Data | RaviOS persistent Docker storage, separate from RootFS. |
| Model store import | Copying an existing Ollama-managed store while preserving its structure. |
| GGUF import | Creating an Ollama model from a standalone GGUF file using a supported workflow. |
