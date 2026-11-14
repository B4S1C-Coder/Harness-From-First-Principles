# Harness From First Principles
Python framework for building LLM agents and harnesses from first principles: agent base class, tool registry / executor, prompt store, context compaction, sandboxed virtual filesystem, logging.

## Goals
- Sequential sub agents
- The harness needs to incorporate more features and tools suitable for software root cause analysis workloads.

## Layout
- `harness/` - the framework
  - `agents/` - agent base class (synchronous)
  - `tools/` - base tool class (framework's representation of OpenAI format), global tool registry and agent specific tool executor
  - `builtin_tools/` - ready-to-use tools (implementations) provided by the framework
  - `llms/` - OpenAI (Completions API) compatible clients (synchronous)
  - `prompts/` - prompt store used for loading and versioning prompts
  - `enums/` - shared enums
  - `sandboxes/` - purpose specific sandboxes used for safe tool execution
  - `shortcuts/` - convenience implementations based on observed usage and patterns
  - `sql/` - sqlite3 query templates for prompt store
  - `compaction.py` - provides context compaction strategies to free up context window
  - `exceptions.py` - application specific exception hierarchy
  - `helpers.py` - helper tools such as safely loading environment variables etc.
  - `limits.py` - dataclasses specifically governing limits, such as tool call limits, etc.
  - `logger.py` - logger that must be used with the framework
- `refs/` - reference material, read-only
- `examples/` - runnable examples of the framework
  - `basic_agent/` - basic agent with dummy tools, a conversation loop and compaction
  - `fs_agent/` - file system agent with real sandboxed file system tools, conversation loop and compaction
  - `basic_agent_without_base.py` - uses the old architecture without base agent and tool executor (no longer works, preserved for legacy reasons)
  - `register_prompts.py` - used to register the prompts that the example agents use
- `experimental/` - experimental work that could introduce changes and features in the framework
  - `subagent/` - main agent and sub agent experiment (sequential agents) with dummy RCA prompt
  - `vfsb_subagent/` - main agent and sub agent (with real file system tools) with a light log analysis load currently suffering from context overflow

## Package Docs
Before editing anything inside a package, read that package's `AGENTS.md` (if it exists). It holds the package's purpose and contracts.

## Commands
- Install: `uv sync`
- Test: `uv run pytest -v`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`

Run the tests and lint before saying a task is done.

## Conventions
- Python version: see `.python-version`. Type hints on all functions.
- Dataclasses for schemas
- Always raise errors from `harness/exceptions.py` ; don't invent ad-hoc exceptions.
- If an error is not covered by `harness/exceptions.py`, consult the user on what should be done: either add a new exception or use an existing one.
- Log through `harness/logger.py`, never `print`.
- Keep modules small; follow the style of neighbouring files.
- Each folder in `examples/` and `experimental/` follow a specific structure, respect and follow that structure whenever working in those directories.
- Use PEP 695 syntax (`def f[T](x: T)`, `class Box[T]`); never import `TypeVar`/`Generic`
- `examples/basic_agent_without_base.py` is legacy and broken. Don't fix, refactor, or import it. Ignore it when reporting lint or test results.
- `experimental/vfsb_subagent/` has a known context-overflow problem. Don't try to fix it unless asked.
- The framework is synchronous. Don't introduce async/await.
- LLM clients target the Chat Completions API. Don't use the Responses API.

## Rules
- Don't change a public interface without updating that package's `AGENTS.md` in the same change.
- Never run `git add` or `git commit` or `git push` or change branches unless explicitly told to do so. Other non-destructive commands are allowed.
- Add or update tests for every behaviour change. Keep existing tests green.
- Exception: `harness/agents` and `harness/llms` has no tests for now (see its AGENTS.md). Don't create tests that need a real LLM.
- Don't add dependencies without asking.
- Never read, print or commit `.env`. Use `.env.example` for new variables.
- Don't touch `refs/` unless asked.
- Run only the tests for the package you changed (`uv run pytest tests/<path> -v`), then the full suite once at the end.
- Make the smallest change that satisfies the task. Ask before refactoring or touching unrelated files.

## Current Working Memory

Read [MEMORY.MD](./MEMORY.MD) before continuing the current investigation-harness work. It records session findings, decision rationale, known failures, current implementation state, and proposals that have not been implemented. Treat it as temporary working memory, not permanent requirements or authorization to implement pending ideas. It may be cleared or replaced when the work moves to a different topic; follow the user's latest instructions and verify the current code.
