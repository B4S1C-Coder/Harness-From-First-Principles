# Working memory: log investigation and context management

Last updated: 2026-11-14.

This is temporary working memory for the current investigation-harness work, not a permanent architecture specification. It may be replaced or cleared when the work changes. Verify the code before relying on implementation details below.

## Status and immediate instruction

The user is pausing implementation to research how an investigation should proceed. The current request is documentation only. Do not implement the proposed next steps below without a new request. No successful end-to-end live investigation has been established in this session; passing unit tests did not establish provider compatibility or investigation quality.

## Goal and representative input

Build a synchronous software RCA harness that can gather evidence, reconstruct a failure sequence, distinguish underlying problems from downstream symptoms, and report uncertainty without endlessly searching or overflowing request limits.

The user's representative on-call prompt is:

> A Hadoop MapReduce application experienced failures during job execution. Relevant application logs are available to your log-analysis specialist. Investigate the logs, reconstruct the sequence of failures, identify the most likely underlying issue, and explain which errors may be secondary symptoms. Cite specific log timestamps and messages. Do not claim a definitive root cause if the evidence is insufficient.

This is deliberately a broad, realistic incident request. The harness should handle it without requiring the user to write a retrieval plan. The user does not consider a larger model necessary merely to search logs; the session has not established model capacity as the root problem.

## Evolution and rationale

1. The original `experimental/vfsb_subagent` used filesystem tools and an open-ended investigation sub-agent. Context growth and repeated retrieval were the motivating problems.
2. An approved plan replaced filesystem access with an ephemeral SQLite dataset and bounded log tools. This was intended to support selective queries and aggregation while keeping bulk evidence out of model context. Merely changing storage did not make the investigation converge.
3. Tool-aware compaction was added to summarize exchanges within a single user turn. The old naive strategy retained user turns, so a long investigation under one user request could remain uncompacted.
4. A pre-request estimate was added, but its one-byte-per-token accounting was far too aggressive for this workload. The user explicitly requested disabling it for a trial. The bypass also disables automatic compaction: those behaviors remain coupled.
5. A six-tool-turn policy plus one summary-only turn was tried for the sub-agent. This bounded tool execution but failed to guarantee a final report: the provider rejected a generated tool call despite tools being disabled.
6. The open-ended `analyze_logs(task)` boundary encouraged the main agent to forward the entire incident. Its description and sub-agent prompt explicitly asked for RCA, so delegation duplicated the main agent's job rather than providing bounded evidence retrieval.
7. The user agreed to try direct investigation despite the context-volume tradeoff. The current main agent owns all log tools and RCA; the smaller model only generates/repairs SQL for focused advanced-analysis requests. This removed a second investigation loop, but another live run still exceeded the provider's request allowance.

## Current implementation

### Experiment and tools

- Entry point: `uv run python -m experimental.vfsb_subagent.run`.
- `run.py` is import-safe and exposes `build_agent(...)` for fake-client testing.
- Main investigator: `openai/gpt-oss-120b`.
- Query-generation helper: `openai/gpt-oss-20b`, isolated from the main conversation.
- No `analyze_logs` tool or investigation sub-agent is wired into the current run. Older sub-agent prompt artifacts remain but are unused by this entry point.
- Main has `log_overview`, `search_logs`, `nearby_logs`, and `advanced_log_analysis` directly.
- `log_backend.py` loads `experimental/data/workspace/app-*.log` into in-memory SQLite at startup and closes it at shutdown. Stores original text, filename, 1-based line, timestamp, level, thread, logger, message; unmatched lines retain null parsed fields. Indexes cover timestamp, level, filename/line.
- Deterministic tools use parameterized SQL. Advanced query execution is read-only via authorizer/query-only mode, with a progress-handler timeout and bounded output.
- Responses are bounded to 20 rows and approximately 4 KiB including allowance for the executor envelope, with explicit truncation. Large output is trimmed by dropping rows.
- `query_helper.py` uses a minimal backend protocol and result dataclass. At most three query attempts, with only the latest failed attempt/error retained for repair. The investigator receives successful SQL and bounded results, or a concise failure, not repair history.
- No new dependencies, KQL implementation, persistent ingestion, or generalized query-generation framework was added.

### Context management

- `SynchronousAgentBase` accepts a compaction callable, defaulting to `naive_compaction`.
- `tool_aware_compaction` retains original system instructions, current user request, and the configured number of complete assistant exchanges. Tool-call batches and results stay together in retained history; incomplete batches are protected.
- Older history is summarized through bounded serialized-text chunks into one rolling summary. Current bounds: 2,500-byte chunks and a 1,500-byte summary; generated summary text is clipped to that bound. This is lossy and not validated for factual preservation by live runs.
- With the check enabled, `step()` estimates serialized messages plus tools at one UTF-8 byte per token, compacts at budget times threshold, then rejects a still-oversized request with an existing harness error.
- **Current experiment settings:** `context_budget=8000`, `compaction_threshold=0.75`, `recent_turns_to_keep=1`, `compaction=tool_aware_compaction`, **`enable_context_check=False`**.
- Consequently, the configured strategy is NOT automatically invoked in this experiment. There is no separate usage-triggered or periodic compaction path.

### Tool-turn limit and finalization

- Base constructor accepts `max_tool_turns`; default is unlimited. It counts assistant tool-call batches, including failed executions, not individual calls in a batch.
- The counter resets on a nonempty `add_user_message` and on `reset`.
- Current main experiment permits **12 tool turns plus one final summary step**.
- After exhaustion, `step()` sends no tools and a temporary system instruction requesting findings, references, hypotheses, and uncertainties. A valid final report remains in history and ends the turn.
- Empty summaries or returned tool calls are rejected before tool dispatch.
- The client omits tool definitions and sends `tool_choice="none"` for an empty tool list.
- **Known limitation:** provider-side generation can still attempt a tool call and fail before a response reaches the harness. No isolated final-synthesis workflow or deterministic evidence fallback has been implemented. The current run can still exit on this failure.

### Prompts and observability

- Prompts focus on responsibilities and tool use rather than ingestion/storage details. The current main prompt explicitly treats the user's mention of a specialist as a request to use its own tools.
- The main owns hypothesis formation, evidence selection, causal reasoning, and the final assessment. Advanced analysis is for concrete evidence queries, not forwarding the entire incident.
- Prompt Markdown is registered in `examples/data/prompts.db`; editing Markdown alone does not update the loaded prompt. The revised main and earlier revised sub-agent prompts were registered during this session. Registration scripts remain available in the experiment.
- `SCMTTAgent` uses the application logger at DEBUG for tool call IDs, names, raw argument strings, result success/error, result byte size, row count, truncation, filename/line references when present, and successful generated queries. Full evidence rows are not logged by this instrumentation.
- These logs include malformed argument and validation failures. Existing input/cached token usage logs remain at INFO.

## Observed failures and what they establish

### Empty-schema provider rejection

Groq rejected `log_overview` with `required present but properties is missing`. The tool had `properties: {}` and `required: []`. Removing the redundant empty `required` field allowed later live runs to execute the tool. The other parameterized tools already listed all properties in `required`; nullable search fields still must be present, with null disabling a filter. One bad tool definition can reject the entire request because all tools are sent together.

### Immediate compaction rejection

The original threshold was effectively **6,000 serialized bytes**, despite being described as 6,000 estimated tokens. A local startup request measured roughly 4,464 bytes before evidence arrived. After the first tool exchange, retaining the system prompt, current request, and latest exchange could preserve the entire conversation. There was nothing to summarize, so compaction returned unchanged history and the recheck raised `Request remains above the context threshold`.

This was not necessarily a summarizer failure. Reusing the same sub-agent on a main-agent retry appended another request to already oversized history. Token counts logged by the main agent between retries were not measurements of the failing sub-agent's request.

### Retrieval quality and ambiguity

Repeated `search_logs` names alone did not prove identical queries. Before argument/result logging, we could not distinguish productive narrowing from repeated evidence, empty results, or validation errors. Small context increases were only clues, not proof of empty results.

Local checks against the dataset found:

- An unfiltered search returned 9 rows before the byte cap; an ERROR search returned 11. Both were truncated and showed only the earliest portion of the dataset.
- `SELECT *` duplicates information: raw text plus extracted timestamp, level, thread, logger, and message. This wastes response/context budget.
- Search ordering returns earliest matches first. No total match count, cursor, or grouped recurring-event summary helps the model decide whether another search adds value.
- Timestamp filters compare strings. An ISO-style `T` separator silently produced no results against stored timestamps with a space. Current prompts specify `YYYY-MM-DD HH:MM:SS,mmm`, but backend normalization/validation has not been fixed.
- A sufficiently large individual row can be dropped entirely by byte bounding; an empty truncated result need not mean no matching evidence.

Later live traces showed a search of app-01 ERROR events followed by an attempted FATAL search around the failure. That is a plausible next investigative step, not an identical-query loop. Another trace used both `level="ERROR"` and `keyword="ERROR"`, a redundant filter for these parsed records, and retrieved 11 truncated app-03 rows in 3,701 bytes.

These observations establish inefficient evidence gathering, not that the model cannot reason. We still need to evaluate whether questions discriminate hypotheses and whether retrieved evidence changes the explanation. SQLite and compaction alone cannot provide that policy.

### Forced summary rejected

After six tool turns in the sub-agent trial, Groq returned HTTP 400: `Tool choice is none, but model called a tool`, with a generated FATAL search. Execution was blocked, as intended, but the desired summary was never produced. Disabling tools is an execution restriction, not a guarantee of successful text generation. Continuing the same tool-heavy conversation with a final instruction proved insufficient in that run.

### Latest direct-investigation failure

The previous successful main-agent response reported 7,140 input tokens. After another search result, Groq rejected the next request with HTTP 413: **TPM limit 8,000; requested 8,576**. The error specifically identifies a tokens-per-minute allowance, not the model's native context-window limit. Do not conflate them or assume waiting will solve a request whose assessed size alone exceeds that allowance. The exact provider accounting was not established in this session.

Automatic compaction was disabled, so history kept growing. A provider usage count describes the prior request and excludes the newly appended assistant/tool exchange. Current error translation reports this 413 as `UnexpectedResponseError`; provider retry/error-classification changes were not implemented.

## Proposed directions — NOT implemented or approved as the next change

The last recommendation was to combine periodic compaction with a better size guard, and keep investigation termination separate:

1. Initially compact every four completed tool turns: summarize the oldest three and retain the latest complete exchange, original instructions, and current request. Replace history only after a valid summary exists. Four is an experimental candidate, not an established optimum.
2. Use an isolated text-only summarization request with evidence represented as data rather than continuing the live tool-call trajectory. This is intended to reduce tool-generation carryover; it is not yet proven to eliminate provider failure.
3. Use the last provider-reported input-token count as a baseline and estimate newly appended messages with headroom. Recalculate appropriately after replacing history; the old baseline cannot blindly describe the compacted request. Exact calibration and provider allowance accounting require research.
4. Maintain an independent total investigation budget that compaction does not reset. If final synthesis fails, return saved findings/evidence deterministically rather than discard the investigation. This fallback does not exist yet.
5. Rolling summaries should preserve observations and references, hypotheses, supporting/contradicting evidence, rejected explanations, and unanswered questions. Avoid converting tentative explanations into facts.
6. Reduce duplicated search fields and return grouped recurring events with counts and representative references. Better evidence density may matter as much as compaction.
7. If an investigation sub-agent is reintroduced, constrain it to bounded evidence questions using structured operations/filters/grouping, rather than an unrestricted RCA task. The main should retain incident interpretation and causal evaluation.

Do not implement a final large compaction only at the end: a request may fail before reaching it. Conversely, a four-turn hard final-answer cutoff may stop a legitimate alternative-hypothesis check. Context growth, tool execution limits, and investigation sufficiency are distinct concerns.

## Validation and working preferences

- The user explicitly forbids tests that send requests to an LLM provider. Use fake clients or stub SDK methods; no live provider smoke tests. Live observations above came from the user's runs.
- Latest implementation validation before this documentation task: 92 tests passed; Ruff passed with `examples/basic_agent_without_base.py` excluded as required by the repository instructions.
- Relevant tests: `test_compaction.py`, `test_log_investigation.py`, `test_investigation_policy.py`, `test_direct_log_agent.py`.
- Tests cover mechanics such as parsing, bounds, read-only execution, timeout, repair isolation, history preservation, tool budget enforcement, debug metadata, SDK argument construction, and direct-investigator wiring. They do not demonstrate live convergence, summary fidelity, or universal provider compatibility.
- Keep diagnostics in the application logger at DEBUG. Keep prompts focused on task and method. Do not solve uncertain investigation behavior by automatically escalating model size.
- Preserve existing synchronous Chat Completions architecture and package contracts. Do not read `.env`, add dependencies, modify `refs/`, or perform git staging/commits without the required authorization.
