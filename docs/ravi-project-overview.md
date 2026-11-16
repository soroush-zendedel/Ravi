# Ravi --- Project Goals and Current Product Direction

**Document status:** Living project overview\
**Scope:** Standalone Ravi project\
**Last updated:** November 17, 2026

## 1. Project Overview

Ravi is being developed as a standalone assistant platform, distributed
as a Docker image.

The long-term goal is for Ravi to become the system assistant for
RaviOS: users should be able to interact with their system in natural
language and ask Ravi to understand requests and carry out appropriate
system operations.

Ravi is not intended to be merely a chat interface or a thin wrapper
around a language model. The current model runtime, Ollama, is an
execution component used by Ravi; it is not the identity or the full
scope of the product.

The project is being developed incrementally. Product capabilities and
behavior should be discussed and clarified before committing to
implementation or architecture decisions.

## 2. Project Scope and Boundaries

### 2.1 Standalone Ravi

The standalone Ravi repository is responsible for Ravi itself and the
functionality that runs inside the Ravi container.

Its scope includes: - Ravi's in-container command-line interface. - Chat
and assistant interaction. - Natural-language interpretation of user
requests. - The ability to use tools and perform permitted actions. -
The assistant capabilities that can be shared by different user
interfaces.

The standalone repository is not responsible for implementing the
host-side RaviOS command or wrapper.

### 2.2 RaviOS Integration

Host-side integration will be implemented separately in RaviOS.

The intended host command is:

``` sh
ravi
```

Conceptually, this command will invoke the CLI inside the
already-running Ravi container:

``` sh
docker exec -it ravi ravi chat
```

This keeps the Ravi application and its in-container behavior separate
from RaviOS-specific host integration.

## 3. Long-Term Goals

### 3.1 Natural-Language System Assistance

Ravi's central long-term purpose is to let users operate their system
through natural language.

Rather than requiring users to know and type every system command
themselves, they should be able to describe what they want to achieve.
Ravi should interpret the request, determine what actions are
appropriate, and carry them out when permitted.

This capability is intended to go beyond answering questions: Ravi
should be able to perform real operations through an execution/tool
layer.

### 3.2 Multiple Ways to Interact

Ravi should not be tied to a single interface.

The terminal is the current interface. A future web interface is also
planned, with Open WebUI being considered as the user-facing interface.
Voice interaction is a future possibility.

Different interfaces should provide access to the same underlying Ravi
assistant capabilities. Open WebUI should act as an interface to Ravi,
not become the core of the product or a required dependency for the CLI.

### 3.3 Multiple Assistant Personalities

Ravi is intended to be the default and system-oriented assistant, but
the platform may eventually support additional configurable
personalities.

Different personalities may have different: - Instructions and
behavior. - Models. - Tools and capabilities. - Permission levels.

The exact design and implementation of multiple personalities have not
yet been decided.

### 3.4 Extensible Assistant Capabilities

The project may eventually incorporate capabilities and integrations
such as tools, harnesses, MCP, and voice commands.

These are areas for future exploration, not finalized implementation
commitments. Their value and role should be evaluated individually as
the product develops.

## 4. Current Capabilities and Direction

At this stage, Ravi supports chat through its terminal interface.

The next important capability under consideration is natural-language
terminal interaction: a user should be able to describe a task in
ordinary language and have Ravi execute the corresponding commands or
operations, subject to permission rules.

This is a shift from a chat-only assistant toward an assistant that can
act on the system.

Open WebUI is being considered for future integration. The current
preference is to start from Open WebUI largely as it is, examine its
features, and decide which features are useful and which can be removed
or left unused. No final integration or feature-selection decision has
been made.

## 5. Permission and Safety Principles

System operation requires an explicit permission model. The following
principles have been agreed upon.

### 5.1 Risk-Based Confirmation

Not every action should require the same level of approval.

-   **Low-risk actions** may run without asking each time. Examples
    include checking system status and listing files.
-   **Riskier actions** should require user confirmation. Examples
    include deleting files or changing network settings.
-   **Highly sensitive or destructive actions** should require explicit
    confirmation. Examples include shutting down the system or
    performing irreversible operations.

The precise classification of actions and confirmation flow remain to be
designed.

### 5.2 Independent Permission Enforcement

Permission enforcement must not depend solely on the language model's
judgment or on text generated by the model.

Ravi's tool or command execution layer must independently enforce
authorization rules before carrying out an operation. The model may
interpret a request and propose an action, but it must not be the sole
authority deciding whether that action is allowed.

### 5.3 Personality-Based Permissions

Permission levels should eventually be configurable per assistant
personality.

For example, different personalities may be granted different levels of
access to tools and system operations. The details of this configuration
are not yet defined.

## 6. Product Principles

The following principles capture the current direction:

1.  **Ravi is the product.** Ollama is currently the model execution
    engine, not the product identity.
2.  **Keep the core independent of its interfaces.** CLI and future web
    or voice interfaces should use shared Ravi capabilities.
3.  **Separate Ravi from RaviOS host integration.** The standalone
    project owns Ravi inside its container; RaviOS will own the
    host-side command and integration.
4.  **Make Ravi capable of acting, not only chatting.** Natural-language
    system operation is a central long-term goal.
5.  **Enforce permissions outside the model.** The execution layer must
    independently check whether an action is allowed.
6.  **Use risk-appropriate confirmation.** Routine actions, risky
    actions, and destructive actions should not all follow the same
    approval flow.
7.  **Allow different personalities to have different permissions.**
    This is a future configurability goal.
8.  **Evolve incrementally.** Discuss and evaluate capabilities
    individually instead of prematurely committing to a large
    architecture or feature set.

## 7. Open Questions

The following topics remain open and should be explored before
implementation decisions are made:

-   How natural-language requests should be translated into executable
    operations.
-   Which tools and command capabilities Ravi should provide initially.
-   How action risk levels should be classified and maintained.
-   How confirmations should be presented and recorded.
-   How personality-specific permissions should be configured.
-   Which Open WebUI features are useful for Ravi and which should be
    omitted.
-   How future voice interaction should fit into the product.
-   Whether and how integrations such as MCP and additional harnesses
    should be incorporated.

These are discussion topics, not settled design decisions.

## 8. Current Status at a Glance

  -----------------------------------------------------------------------
  Area                                Current status
  ----------------------------------- -----------------------------------
  Product form                        Standalone Docker image

  Current interface                   Terminal CLI

  Current interaction                 Chat

  Model runtime                       Ollama

  Main long-term role                 Natural-language system assistant
                                      for RaviOS

  Natural-language command execution  Planned capability under
                                      consideration

  Host-side `ravi` command in RaviOS  Separate RaviOS responsibility; not
                                      part of the standalone repository

  Open WebUI                          Under consideration as a future
                                      interface

  Voice interaction                   Future possibility

  Multiple personalities              Long-term direction

  Personality-specific permissions    Agreed principle; design not yet
                                      defined

  Independent permission enforcement  Agreed principle

  Risk-based confirmations            Agreed principle

  MCP and other integrations          Future exploration; no
                                      implementation decision
  -----------------------------------------------------------------------

------------------------------------------------------------------------

This document records the product direction and decisions discussed so
far. It is intended to evolve as Ravi's goals, capabilities, and design
decisions become clearer.
