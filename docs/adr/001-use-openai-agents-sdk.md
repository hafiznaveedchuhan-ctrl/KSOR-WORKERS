# ADR 001: Use the OpenAI Agents SDK

## Status
Accepted

## Context
The demo needs an agent that can call a remote MCP server's tools
(`MCPServerStreamableHttp` transport) and one that plainly cannot, under
identical instructions, with minimal code.

## Decision
Use the `openai-agents` package (`agents` import). It ships a native
`agents.mcp.MCPServerStreamableHttp` client — connect it, pass it to
`mcp_servers=[...]` on an `Agent`, and `Runner.run` handles tool-call
orchestration. The ungrounded worker is the same `Agent`/`Runner` shape with
`mcp_servers` simply omitted, so the two scripts stay structurally identical
and only differ where the demo needs them to.

## Alternatives considered
- **Raw `openai` SDK + a hand-rolled MCP client** — more code, and the
  grounded/ungrounded scripts would diverge in more than "has tools or not,"
  weakening the comparison.
- **LangChain / LlamaIndex** — heavier dependency surface for a two-script
  demo; no capability this task needs that the Agents SDK lacks.

## Consequences
Locked to the `openai-agents` package's MCP client shape and to OpenAI-hosted
models for `Agent(model=...)`. Acceptable — the demo's point is grounding via
MCP, not model portability.
