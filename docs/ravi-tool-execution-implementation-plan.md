# Ravi --- Initial Tool Execution Implementation Plan

**Document status:** Initial implementation plan\
**Scope:** Standalone Ravi project, starting with the terminal
interface\
**Last updated:** November 17, 2026

## 1. Objective

The first implementation milestone is to evolve Ravi from a chat-only
terminal assistant into an assistant that can select and execute
approved tools in response to natural-language requests.

The initial work will focus on the terminal interface. However, tool
execution and assistant capabilities must not be designed as CLI-only
features.

**Core principle:** The CLI and Open WebUI are different interfaces to
the same Ravi assistant. They must use the same underlying assistant
capabilities and tool-execution behavior.

Open WebUI is not required for this milestone. It can be considered
later as another interface to Ravi.

## 2. Target Interaction Flow

The intended interaction is:

1.  The user makes a request in the terminal.
2.  Ravi interprets the request.
3.  The model selects an appropriate tool and provides the required
    arguments.
4.  A permission-enforcement layer independently checks whether the
    requested operation is allowed.
5.  If permitted, the tool-execution layer runs the operation.
6.  The result is returned to Ravi.
7.  Ravi interprets the result and responds to the user.

The model must not execute arbitrary commands directly. Tool execution
must happen through controlled application functionality.

## 3. Implementation Stages

### Stage 1 --- Inspect the Existing Ravi CLI

Before changing code:

-   Review the current repository structure.
-   Identify how the CLI starts and handles chat.
-   Identify how Ravi currently communicates with Ollama.
-   Locate the parts of the application responsible for conversation
    flow and model responses.

The purpose is to understand the existing implementation and make the
smallest appropriate change. No large architectural redesign is required
at this stage.

**Expected outcome:** A clear understanding of where tool selection and
execution can fit into the existing assistant flow.

### Stage 2 --- Introduce Tool Execution

Add the ability for Ravi to work with a defined set of tools.

Initially, tools should be explicit application capabilities rather than
unrestricted shell commands. Each tool should have a defined purpose and
clearly specified inputs.

The first tools should be limited to low-risk system inspection, such
as:

-   Displaying system information.
-   Checking disk space.
-   Checking memory usage.
-   Listing files and directories.
-   Displaying network status.

**Expected outcome:** Ravi can invoke a small set of predefined tools
and receive their results.

### Stage 3 --- Add Independent Permission Enforcement

Introduce permission checks before tools are executed.

Important requirements:

-   Permission decisions must be enforced by Ravi's
    application/tool-execution layer.
-   The system must not rely solely on the model's own judgment or
    generated text.
-   Low-risk operations may run without asking each time.
-   Riskier operations should require user confirmation.
-   Highly sensitive or destructive operations should require explicit
    confirmation.

The initial inspection tools should use the low-risk path. More
sensitive operations can be introduced in later stages.

**Expected outcome:** A tool cannot run unless the independent
permission layer allows it.

### Stage 4 --- Connect Tool Selection to the Model

Allow the model, through Ollama, to request the use of an available tool
when appropriate.

Ravi should:

-   Make the available tools and their purposes known to the model.
-   Receive the model's tool request and arguments.
-   Validate the request against the tools actually registered in Ravi.
-   Pass the request to permission enforcement before execution.

The model may propose an operation, but it must not bypass tool
validation or permission enforcement.

**Expected outcome:** Ravi can decide when a tool is useful and request
it through a controlled mechanism.

### Stage 5 --- Return Tool Results to the Assistant

After a tool runs:

-   Capture its result.
-   Return the result to the assistant conversation.
-   Let the model interpret the result.
-   Present a useful response to the user in the terminal.

The assistant should distinguish between a successful operation, an
operation that failed, and an operation that was denied or requires
confirmation.

**Expected outcome:** The user receives an understandable answer based
on the actual tool result, rather than only seeing raw command output.

### Stage 6 --- Complete the Terminal Experience

Refine the CLI interaction so that users can naturally request
operations and follow up on the results.

The terminal should support a coherent interaction cycle:

**Request → Tool selection → Permission check → Execution → Result →
Assistant response**

This stage focuses on the user experience of the terminal interface, not
on adding a web interface.

**Expected outcome:** Ravi can perform basic, permitted
system-inspection tasks through natural-language terminal interaction.

## 4. Shared Assistant, Multiple Interfaces

The implementation must preserve this product direction:

-   The CLI is the first interface.
-   Open WebUI may become a future interface.
-   Other interfaces, including voice, may be considered later.
-   Interfaces should not contain separate implementations of Ravi's
    assistant capabilities.
-   Tool definitions, execution behavior, and permission enforcement
    should belong to Ravi rather than being duplicated inside each
    interface.

Open WebUI is therefore not a dependency for the initial implementation.
The goal is to make the assistant capabilities reusable by a future
interface.

## 5. Out of Scope for This Milestone

To keep the first milestone focused, the following are not required now:

-   Integrating Open WebUI.
-   Implementing voice interaction.
-   Supporting multiple assistant personalities.
-   Implementing personality-specific permission configuration.
-   Adding unrestricted shell access.
-   Integrating MCP or other external tool ecosystems.
-   Designing a comprehensive plugin or extension system.

These topics may be explored separately as Ravi evolves.

## 6. Completion Criteria

The initial milestone can be considered complete when:

1.  A user can make a natural-language request through the Ravi CLI.
2.  Ravi can select an appropriate predefined inspection tool.
3.  The requested tool and its arguments are validated by Ravi.
4.  An independent permission layer checks the operation before
    execution.
5.  The tool executes only when permitted.
6.  Its result is returned to the assistant.
7.  Ravi explains the result to the user.
8.  The tool and permission capabilities are not tied exclusively to the
    CLI.

## 7. Working Approach

Proceed incrementally:

1.  Inspect the existing code.
2.  Discuss the smallest change needed for the next stage.
3.  Implement that stage.
4.  Test it before moving on.

Do not introduce a large architecture or implement future features
prematurely. Keep the first working version small, understandable, and
suitable for later extension.

------------------------------------------------------------------------

This document describes the first implementation milestone and its
intended sequence. It does not prescribe a detailed software
architecture or settle implementation choices that have not yet been
discussed.
