# Ravi Architecture

**Open Source AI Infrastructure**

*Powered by Openness. Built for Everyone.*

Document version: 1.2
Status: Architecture baseline and development proposal
License: MIT
Initial consumer: DevOS; Ravi must remain an independent project.

> This document describes both the intended architecture and a historical deployment baseline. Section 23 records infrastructure details from an earlier host project; those values are not a statement of the current deployment. Verify service names, endpoints, and persistent volumes before any migration.

---

## 1. Executive summary

Ravi is an independent, modular, extensible, open-source infrastructure for connecting, managing, coordinating, and using AI technologies. It provides a consistent layer between applications and cloud providers, inference engines, and other AI services.

Ravi is more than an API gateway, but it should not rebuild mature tools. Its job is to integrate existing tools as an independent infrastructure and manage their configuration, communication, and lifecycle.

Planned capabilities include:

- Cloud language and multimodal models.
- Local inference engines.
- Model selection and routing.
- Provider integration.
- Coordination among AI services.
- Agent and tool integration.
- Memory and context services.
- Infrastructure configuration and deployment.
- Health and service status monitoring.
- A standard API for consumer applications.

**Ravi belongs to no single consumer project. Different projects should be able to use it.**

DevOS is an important early consumer, but Ravi must run independently on a server, personal computer, virtual machine, or Docker environment.

## 2. Vision and mission

### Vision

Build an open infrastructure that separates access to AI from any one provider, model, inference engine, or operating environment. Ravi should coordinate the AI ecosystem, reduce the complexity of connecting tools, and expose their capabilities through standard interfaces.

### Mission

Provide a platform where:

1. Developers can add a provider without changing every consumer application.
2. Applications can switch between local and cloud models.
3. Multiple models and providers can follow shared policies.
4. AI capabilities can be offered as independent services.
5. Developers can install, run, extend, and customize Ravi.
6. Mature tools can work together without unnecessary rewrites.
7. Ravi does not depend on a mandatory commercial service or an owner-controlled central server.

## 3. Foundational design principles

### 3.1. Independence

Ravi should have its own repository, development lifecycle, versioning, images, documentation, configuration, tests, and release process. Ravi files, services, databases, and internal settings should not be copied into DevOS or other consumer repositories. Consumers should connect through APIs and standard protocols, using an internal network when appropriate.

### 3.2. Open source

Ravi is released under the MIT License. Use, modification, development, distribution, and independent deployment are allowed under that license. Ravi must not require a paid subscription, proprietary license, commercial service, or central server owned by its maintainers.

### 3.3. Provider independence

No provider should become an irreplaceable component. Cloudflare, Google, OpenAI, Anthropic, and other providers should be attachable through independent integrations. Losing access to one provider must not disable all of Ravi.

### 3.4. Cloud and local AI

Ravi should support both cloud models accessed through external APIs and local models running on user-owned hardware or private infrastructure. They should be usable under shared routing and usage policies.

### 3.5. Modularity

Each capability should be an independent module where practical. Adding a feature should not require rewriting the core or making broad changes across unrelated modules.

### 3.6. Reuse instead of rebuilding

When a mature tool already provides a capability, Ravi should integrate it rather than create a parallel implementation. For example, Ravi should use LiteLLM's provider and model management, a local engine's own management API, and an existing memory or vector database when they meet the need. Ravi should focus on connections, coordination, and integration. This lowers maintenance cost and keeps Ravi aligned with improvements in its underlying tools.

### 3.7. Independent use

Ravi must not depend on DevOS. Any person or project should be able to deploy it with Docker Compose or another documented method.

### 3.8. Security and data ownership

Deployment administrators control secrets, API keys, request history, and user data. Ravi must not send data to external services without configuration and explicit authorization.

## 4. Ravi's place in the overall architecture

The following is a conceptual architecture, not a required process layout:

```text
                 APPLICATIONS
                       |
       +---------------+---------------+
       |               |               |
     DevOS          Web Apps        Other Projects
       |               |               |
       +---------------+---------------+
                       |
                       v
              +------------------+
              |       RAVI       |
              | Integration      |
              | Configuration    |
              | Routing          |
              | Coordination     |
              | Policies         |
              | Health Monitoring|
              +------------------+
                       |
          +------------+------------+
          |            |            |
          v            v            v
      CLOUD AI      LOCAL AI     AI SERVICES
      LiteLLM        Ollama       Agent Tools
      Gemini         vLLM          Memory
      Cloudflare     llama.cpp     Workflows
      OpenAI         Local APIs    Other Services
          +------------+------------+
                       |
                       v
              MODELS AND TOOLS
```

Ravi may consist of several independent services. Capabilities do not all need to live in one process or container.

## 5. Proposed Ravi architecture

### 5.1. Ravi Core

The core coordinates Ravi's components. Responsibilities include managing Ravi-level configuration, discovering connected services, tracking service status, coordinating infrastructure, checking version compatibility, exposing health information, managing common settings, and providing consistent consumer interfaces. Ravi Core should not reimplement the internals of underlying tools without a clear need.

### 5.2. Integration Layer

The Integration Layer connects and coordinates tools. Each tool can have its own adapter or connector where needed. Responsibilities include connecting to APIs, managing endpoints, discovering capabilities, checking service health, coordinating settings and communication, converting formats when necessary, and keeping consumers independent from underlying implementations.

An adapter should provide a stable Ravi integration point without reimplementing the full feature set of the tool it connects.

### 5.3. AI Gateway

Ravi can use an existing gateway such as LiteLLM and expose its capabilities through Ravi's API. Infrastructure-level responsibilities include connecting to the gateway, exposing consumer endpoints, coordinating access and service settings, checking gateway health, and making routing policies available. Ravi should not rewrite LiteLLM merely to own a gateway implementation.

### 5.4. Provider management

Provider management should be handled by a dedicated underlying tool wherever possible. LiteLLM can provide much of this functionality in the initial release. Initial providers include Cloudflare Workers AI, Google Gemini, OpenAI, Anthropic, and other OpenAI-compatible services. Ravi coordinates the integrations; it does not need to recreate all provider-management screens and operations.

### 5.5. Local AI integration

Local inference is a major Ravi goal. Engines to evaluate include Ollama, vLLM, llama.cpp, LocalAI, and other engines with connectable APIs. Ravi can discover local endpoints, connect to existing engines, discover available models when possible, check runtime status, coordinate with the gateway, and route between local and cloud services.

The first release should not build another inference engine, GPU manager, or model downloader. Prefer the local engine's own management interface when it is suitable.

### 5.6. Model registry

Ravi may maintain a lightweight registry of connected model metadata without replacing the model management of underlying tools. Possible metadata includes model ID, provider, inference engine, model type, known capabilities, connection status, and routing information. Read it from underlying APIs when possible to avoid maintaining duplicate configurations.

### 5.7. Intelligent routing

Ravi can use routing already available in its gateway and add higher-level policies when a real need exists. Potential criteria include expected quality, latency, cost, availability, capacity, local or cloud execution, privacy policy, and model capabilities.

Possible policies include `local-first`, `cloud-first`, `lowest-cost`, `lowest-latency`, `quality-first`, `balanced`, and `privacy-first`. If an underlying tool provides a suitable policy, Ravi should configure and use it instead of building a parallel routing engine.

### 5.8. AI services

Ravi may integrate embedding, reranking, speech recognition, text-to-speech, image understanding and generation, document processing, structured output, and vision services. Each service must have a clear responsibility: Ravi should define whether it only supplies a connector or also operates the service.

### 5.9. Agent integration

Ravi may eventually coordinate agents that use registered models, tools, and services. It should evaluate existing open-source agent frameworks before building a new parallel framework. Integrate or develop only after a concrete need is established.

### 5.10. Memory and context integration

Use the same approach for conversation memory, vector databases, retrieval-augmented generation, context management, and long-term memory: evaluate suitable existing tools and integrate them where appropriate. Each consumer project needs an independent memory space, access policy, and data boundary. Memory sharing requires explicit permission and policy.

## 6. Underlying tools and management interfaces

**Ravi should not rebuild the management interfaces of underlying tools.** LiteLLM and inference engines may already provide administration interfaces, management APIs, usage reports, and monitoring. Use the official interface directly whenever possible.

Ravi is responsible for documenting access, storing service connection settings, coordinating deployment, checking service availability, documenting tool interactions, and providing required integration. A small page that lists connected services and links to their official interfaces may be useful. A parallel management console is outside Ravi's current scope.

Develop a new management feature only when the underlying tool lacks it and a clear operational need exists.

**Use an existing capability by integrating it correctly; do not create a duplicate by default.**

## 7. Infrastructure and data management

Ravi needs stable, maintainable infrastructure.

### PostgreSQL

Use PostgreSQL for Ravi-specific data only when needed. Possible data includes Ravi-level settings, deployment metadata, connected service information, Ravi-specific policies, and consumer project metadata if that feature is implemented. Do not copy data that an underlying tool already manages correctly.

### Redis

Use Redis when needed for cache, temporary state, process coordination, or rate limits. Redis should not be an architectural requirement without a concrete use case.

### Object storage

Consider object storage if Ravi needs to retain files, multimodal outputs, or large data.

### Migrations and backups

Every Ravi-owned schema change needs a migration. Define backup, restore, backup integrity checks, retention, versioned migrations, and disaster recovery documentation. Back up underlying tools with their own supported procedures.

## 8. API and consumer contract

The API is Ravi's most important boundary of independence. Consumer applications should not need to know Ravi's internals or the implementation details of connected tools.

Example request:

```http
POST /v1/chat/completions
Authorization: Bearer <PROJECT_API_KEY>
Content-Type: application/json
```

```json
{
  "model": "balanced",
  "messages": [{"role": "user", "content": "Hello Ravi"}]
}
```

Ravi or its connected gateway chooses a destination according to the configured policy. Proposed initial routes are `/v1/models`, `/v1/chat/completions`, `/v1/embeddings`, `/v1/responses`, `/health`, and `/ready`. Future routes such as `/v1/agents`, `/v1/memory`, `/v1/tools`, `/v1/tasks`, `/v1/audio`, and `/v1/images` should be advertised only after they are implemented.

### API keys and projects

If Ravi needs consumer management, it may issue an independent key for each project. Possible restrictions include allowed models and services, request quotas, usage limits, rate limits, privacy policy, and expiration. Reuse the gateway's implementation when it provides these capabilities appropriately.

## 9. Security

Security must be part of the architecture from the start. Requirements include:

1. Keep provider keys in secure deployment storage and out of images.
2. Never write secrets to logs.
3. Keep master keys out of consumer code.
4. Support key revocation and rotation.
5. Restrict access by project and role.
6. Validate inputs.
7. Protect against abuse and excessive requests.
8. Manage timeouts and concurrent requests.
9. Do not expose administration interfaces to the public internet unintentionally.
10. Record security events.
11. Keep consumer data isolated.

Use security capabilities provided by underlying tools while securing Ravi's own communication boundaries. Do not expose local management interfaces without authentication or through unsafe configuration.

## 10. Independent deployment and Docker

Design Ravi to be deployed independently. A conceptual deployment may include Ravi Core, a gateway such as LiteLLM, optional local engines, and optional infrastructure. This does not require one container per component. Run each tool according to its supported deployment method.

### Shared central deployment

A central Ravi instance can serve several projects. This offers centralized management, shared providers and models, less duplicated infrastructure, and simpler maintenance.

### Independent deployment

Each project can deploy its own Ravi, services, and data. Each deployment needs independent configuration, keys, data, versioning, and lifecycle.

### Separate images from configuration

Docker images contain software and versioned dependencies only. Keep `.env`, secrets, API keys, master keys, deployment-specific settings, database connection details, and persistent service data outside images. Never commit secrets or private data to Git.

## 11. GitHub repository structure

The repository can grow toward this structure as modules acquire clear responsibilities, contracts, and tests:

```text
ravi/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── ROADMAP.md
├── docs/ (architecture, API, deployment, security, integrations, development)
├── deploy/ (docker, compose, examples)
├── config/ (examples, schemas)
├── src/ (core, integrations, providers, local_ai, registry, routing, policies,
│         auth, observability)
├── tests/ (unit, integration, contract, end-to-end)
├── scripts/
└── .github/workflows/
```

Do not create every directory in the first release without a real module behind it. Choose a language and framework after technical evaluation. Python is a possible fit for coordination and integration, but the chosen technology should not force Ravi to rewrite existing tools.

## 12. Versioning and releases

Ravi needs an independent release cycle. Recommended practices include Semantic Versioning, GitHub Releases, Docker image releases, GitHub Container Registry, a changelog, migration notes, and automated pre-release checks.

Example versions are `v0.1.0`, `v0.2.0`, `v0.5.0`, and `v1.0.0`. Images should be reproducible and identifiable. Do not use a floating tag such as `latest` as the only deployment option. Production deployments should pin a version and have a rollback path.

## 13. Testing, monitoring, and reliability

Design Ravi to be testable from the beginning. Test categories include unit, integration, API contract, adapter, routing, authentication, Docker build, and end-to-end tests. Underlying integrations should be testable with mocks and, when deployment administrators provide credentials, against real services.

Monitoring should provide health and readiness checks, structured logging, request IDs, metrics, error tracking, and latency monitoring. Prefer official monitoring in underlying tools over an unnecessary parallel system. Respect privacy when logging; storing complete prompts and responses should not be mandatory by default.

## 14. Development roadmap

Develop Ravi in stages.

### Stage 0: Foundation

Create an independent repository, select an architecture, set coding standards and API contracts, define Docker images and Compose deployment, separate configuration and secrets, establish initial CI, document the architecture, and set versioning policy. **Exit criterion:** Ravi can build and run independently.

### Stage 1: Gateway MVP

Integrate LiteLLM, Cloudflare Workers AI, and Gemini; use LiteLLM's management interface; manage deployment settings; provide an OpenAI-compatible API, health checks, logging, and real API tests. **Exit criterion:** An external application receives valid responses without knowing the provider details.

### Stage 2: Deployment and multiple projects

Evaluate project management in underlying tools, manage keys and usage limits at the appropriate layer, define model access policy and independent settings, and document shared and independent deployments. **Exit criterion:** Multiple projects can safely use shared Ravi without interfering with one another.

### Stage 3: Local AI integration

Add adapters for Ollama and vLLM, discover local engines and endpoints, discover model capabilities, monitor health, and support local-first routing. **Exit criterion:** A consumer can use local and cloud models through Ravi.

### Stage 4: Intelligent routing

Evaluate gateway routing, define any additional policies, model priorities and fallback, cost, speed and privacy policies, record selection reasons, and test provider outages. **Exit criterion:** Ravi uses underlying routing and adds higher-level logic only where needed.

### Stage 5: Integration expansion

Evaluate open-source tools and connect embedding, reranking, audio, vision, and document processing services. Assess agent frameworks, memory, and RAG tools, and document each integration. **Exit criterion:** New services can be added without rewriting existing capabilities.

### Stage 6: Agent and memory integration

Select an agent framework, connect a tool registry and workflow engine where needed, connect memory and vector database services, and define context management, permissions, and audit trails. **Exit criterion:** Agents use connected models and tools under explicit access policies.

## 15. Project success criteria

Measure success by more than the number of providers or models. Ravi should support independent deployment; shared use by several projects; independent deployment per project; cloud providers and local engines; a stable documented API; consumer independence from internals; isolated secrets and deployment data; upgrades and rollback; automated critical-path tests; modular growth; official management interfaces; minimal duplication; no mandatory commercial Ravi service; and adequate developer documentation.

## 16. Design outcomes to avoid

- Do not make Ravi depend on DevOS.
- Do not make Ravi merely a new name for LiteLLM.
- Do not rebuild mature capabilities or create a parallel LiteLLM console.
- Do not create an incompatible parallel model-management system.
- Do not require a single provider.
- Do not put secrets in Docker images.
- Do not share consumer data without a defined policy.
- Do not let future features require a core rewrite.
- Do not delete existing data during installation or upgrade.
- Do not advertise a feature as ready before it is implemented.
- Do not leave version-dependent patches without tests and documentation.
- Do not rewrite an existing tool merely because of personal preference.

## 17. Ravi and DevOS

DevOS is an important early consumer, but the relationship must remain standard and independent. DevOS can use Ravi's model API, expose local models to applications through Ravi, connect agents to Ravi tools, and use Ravi routing and future services.

Ravi must not depend on DevOS libraries, internal files, or directory layout. Ravi should still run if DevOS is removed. DevOS should not need to copy or rebuild Ravi infrastructure after an update. Another project should need only Ravi's API and deployment documentation.

## 18. Ownership and contributor community

Ravi is a public open-source project. The repository should include a license, README, contribution guide, code of conduct, security policy, changelog, and roadmap. Follow the MIT License in every release. Independent contributors should be able to participate, and documentation should let people other than the original creator install, run, extend, and maintain Ravi. The project should not depend on undocumented knowledge held by one person.

## 19. Product definition

**Ravi is independent, modular, open-source infrastructure for connecting, coordinating, routing, and using AI technologies. It makes providers, cloud models, local engines, and intelligent services available to applications through an integrated architecture.**

Ravi is built for everyone. DevOS is one of its first consumers.

## 20. Proposed decisions

| Topic | Proposed direction |
|---|---|
| Project | Ravi |
| Type | Open Source AI Infrastructure |
| License | MIT |
| Repository and image | Independent and public |
| API | Independent and documented |
| Initial gateway | LiteLLM |
| Initial providers | Cloudflare Workers AI and Gemini |
| Gateway administration | Official LiteLLM interface |
| Database | Only when Ravi needs one |
| Cache | Redis when needed |
| Deployment | Docker Compose |
| Deployment modes | Shared and independent |
| Local models | Ollama and vLLM in later stages |
| Routing | Reuse existing capabilities and extend only when needed |
| Agents and memory | Integrate existing tools in later stages |
| Custom management console | Outside current scope |
| Releases | GitHub Releases and GHCR |

## 21. First expected development deliverable

The first task is a real, runnable Ravi baseline, not every planned capability at once. It should include an independent repository, buildable image, independent Compose configuration, external configuration, secret management, correct persistent volumes, a LiteLLM gateway, Cloudflare and Gemini integrations, LiteLLM's official management interface, health and readiness checks, automated tests and real API tests, installation and consumer documentation, GitHub Actions for test/build, and an initial release through GitHub Releases and GHCR.

Do not destroy, move, or deprive any existing project of its data while developing this baseline. If current infrastructure is migrated, plan the work, preserve all data, and maintain a rollback path.

## 22. Closing statement

Ravi should be built with minimal reinvention and maximum reuse of mature tools. Do not spend months rebuilding a console that LiteLLM already provides or reimplementing the management features of a local engine. Let each tool own its specialized responsibility and make their interaction simple, standard, and reliable.

Use an existing suitable tool. Build an integration layer when tools cannot communicate. Develop a capability only when an important need is not already met. That is the difference between an independent product and a collection of incomplete copies.

**Ravi does not have to do everything itself; it has to connect everything correctly.**

*Ravi — Intelligence, Everywhere.*

---

## 23. Historical implementation baseline

This section records the deployment state that was documented before Ravi's independent repository was assembled. It is retained as migration context, not as a current deployment claim. Preserve useful work and data, but re-check all details before relying on them.

### 23.1. Earlier development environment

The earlier environment ran on Windows with Docker. LiteLLM was hosted alongside another project. The intended next step was a controlled move to Ravi's own repository, without deleting or disrupting the existing services or data.

### 23.2. Earlier Docker infrastructure

The historical setup recorded three primary services:

| Service | Responsibility |
|---|---|
| `litellm-proxy` | LiteLLM and its API |
| `litellm-redis` | Redis |
| `litellm-postgres` | PostgreSQL |

Recorded versions were LiteLLM `ghcr.io/berriai/litellm:v1.106.6`, Redis 7, and PostgreSQL 18. The API was documented at `http://127.0.0.1:4000`, with `config.yaml` mounted from the host. The recorded Docker network was `litellm-network`.

The old persistent volume names were `soroush-zendedelgithubio_redis_data` and `soroush-zendedelgithubio_postgres_data`. These names are historical and may differ from the current project. They may contain persistent data; do not remove or rename them during migration without an explicit backup and recovery plan.

### 23.3. Cloudflare Workers AI integration

The earlier LiteLLM setup connected to Cloudflare Workers AI using `CLOUDFLARE_AI_BASE_URL` and `CLOUDFLARE_API_TOKEN`. The eight model IDs recorded at that time were:

| LiteLLM alias | Cloudflare model |
|---|---|
| `cf-gpt-oss-20b` | `@cf/openai/gpt-oss-20b` |
| `cf-gpt-oss-120b` | `@cf/openai/gpt-oss-120b` |
| `cf-nemotron-120b` | `@cf/nvidia/nemotron-3-120b-a12b` |
| `cf-gemma-4-26b` | `@cf/google/gemma-4-26b-a4b-it` |
| `cf-qwq-32b` | `@cf/qwen/qwq-32b` |
| `cf-deepseek-r1-32b` | `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` |
| `cf-qwen3-30b` | `@cf/qwen/qwen3-30b-a3b-fp8` |
| `cf-glm-4.7-flash` | `@cf/zai-org/glm-4.7-flash` |

Multiple model aliases do not create separate Cloudflare quotas. Models using the same account and token remain subject to that account's limits. A routing group such as `cloudflare-coding`, `gemini-pool`, or `coding` should be introduced only when supported by the provider and gateway behavior.

### 23.4. Earlier Google Gemini integration

Gemini was configured as a provider alongside Cloudflare. Preserve the integration, but use current upstream model IDs. Ravi's compatibility aliases and validation behavior are documented in [the remediation record](../../plans/ravi-remediation.md).

### 23.5. Cloudflare transformation patch

The earlier integration found that array-form `messages.content` containing text blocks was not accepted consistently by the Cloudflare transformation in LiteLLM. A patch was created at `docker/litellm/transformation.py` to join valid text blocks into a string and call the original transformation through `super()`.

The patch was intentionally narrow: only a non-empty list consisting entirely of `{type: "text", text: <string>}` blocks was normalized. Other, including multimodal or mixed, content was preserved. The patch was designed for synchronous and asynchronous use.

The old deployment mounted the patch at the version-specific path below:

```text
/app/.venv/lib/python3.13/site-packages/litellm/llms/cloudflare/chat/transformation.py
```

That path is historical. The current project uses a derived LiteLLM image that discovers the installed package location before applying the patch.

### 23.6. Historical patch verification

The earlier record states that the host patch was mounted read-only in the real container, that the runtime source referenced the mounted file, and that `CloudflareChatConfig` loaded the override with LiteLLM `v1.106.6`. It also records rebuilding the proxy and inspecting the mount. These results describe that earlier environment and have not been reconfirmed during the present static editing pass.

### 23.7. Historical API requests

The earlier record documented successful requests to `http://127.0.0.1:4000/chat/completions` for plain text and array-form text, both returning HTTP 200. It noted that those requests did not cover all message shapes, multimodal content, streaming, or every Cloudflare model. Those tests were historical and were not repeated in this pass.

### 23.8. Historical secrets

The earlier LiteLLM container used `LITELLM_MASTER_KEY`, `CLOUDFLARE_AI_BASE_URL`, and `CLOUDFLARE_API_TOKEN`. Real values must never be added to this document, images, or Git. Keep provider and gateway secrets in deployment configuration and determine which layer owns each variable during migration.

### 23.9. Historical operational checks

The earlier notes record successful Compose configuration validation, patch mount inspection, runtime class loading, secret presence, LiteLLM startup logs, no pending migration at that time, and real plain-text and array-content API requests. Convert relevant checks into repeatable tests for the independent Ravi repository. The checks were not run during the current editing pass.

### 23.10. Historical component status

| Component | Earlier recorded status | Notes |
|---|---|---|
| Docker Compose | Running | LiteLLM infrastructure |
| LiteLLM | Running | `v1.106.6` |
| Redis | Present | Redis 7 |
| PostgreSQL | Present | PostgreSQL 18 |
| Cloudflare Workers AI | Connected | Eight model IDs recorded |
| Gemini | Configured | Cloud provider |
| Cloudflare transformation patch | Implemented | Previously mounted read-only |
| Runtime patch verification | Reported complete | Historical result |
| Plain-text API request | Reported successful | HTTP 200 |
| Array-text API request | Reported successful | HTTP 200 |
| Independent Ravi Core | Not implemented in that baseline | Future development |
| Independent repository and image | Not yet created in that baseline | Initial objective |
| Ravi Integration Layer | Not implemented in that baseline | Roadmap |
| Local AI, agents, and memory | Planned | Evaluate existing tools first |
| Ravi-owned routing | Not implemented in that baseline | Evaluate LiteLLM first |

### 23.11. Migration requirements

Treat migration as a separate, controlled project. Preserve the LiteLLM version until an upgrade has been planned and tested; model/provider configuration; Cloudflare and Gemini settings without secrets; the Cloudflare patch and its tests; PostgreSQL and Redis data as required; existing volumes; network settings; consumer API endpoints; authentication information; and access policies.

Do not begin migration by deleting old services. First back up configuration and persistent data, record containers, volumes, and networks, create an isolated Ravi deployment, transfer configuration and the patch in a controlled way, verify provider compatibility, run API tests, compare behavior, plan consumer endpoint changes, and preserve rollback. Keep the earlier deployment usable until the independent deployment has been fully tested.

### 23.12. Remaining roadmap from the earlier baseline

1. Stabilize the gateway: keep the patch versioned, add automated transformation tests, cover synchronous and asynchronous paths, assess mixed and multimodal content, document the LiteLLM version and patch process, and evaluate contributing the fix upstream.
2. Establish the independent repository: transfer required files and documentation with history where practical, separate configuration from code and images, create independent Compose deployment, and allow coexistence during migration.
3. Complete the first independent deployment: retain LiteLLM as gateway, include PostgreSQL and Redis only with defined need and data policy, transfer provider settings, apply the patch reproducibly, test API and health, and use LiteLLM's official interface.
4. Prepare external consumers: document endpoints and authentication, provide Python and JavaScript examples, explain model use, and test a separate consumer project.
5. Grow Ravi Core gradually after the gateway and deployment are stable. Do not duplicate LiteLLM merely to have a custom core.

### Historical summary

The earlier starting point was not an empty project: it documented a running LiteLLM deployment, Redis and PostgreSQL, Cloudflare and Gemini configuration, a Cloudflare message patch, and two successful historical API requests. Preserve that work when migrating to an independent, publishable, extensible open-source product.

The next stage is not to rewrite LiteLLM or create another management console. It is to establish Ravi as an independent layer for integrating, deploying, and coordinating existing tools.

*Ravi — Intelligence, Everywhere.*
