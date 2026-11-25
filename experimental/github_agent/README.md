# GitHub issue agent

Ask about a known GitHub issue by URL or by owner, repository, and issue number.
The agent uses the hosted GitHub MCP server's `issue_read` tool for issue details
and comments. For library documentation, it can also resolve a library name
and query its docs through the hosted Context7 MCP server.

Set `GITHUB_TOKEN` to a personal access token with read access to the target
repository's issues and `CONTEXT7_API_KEY` to your Context7 API key. Both are
required at startup. Set `MODEL`, `MODEL_URL`, and `API_KEY` for a Chat Completions
provider that supports tool calls. Export the variables or use the repository-root
`.env` file. The variable names are listed in `.env.example`.

From the repository root, run:

```sh
uv run python -m experimental.github_agent.run
```

For example, ask “Summarize owner/repo#123 and its comments,” substituting your
repository and issue number. Type `quit` or press Ctrl-D to end the session.

# Sample Conversation
## User Message 1
Can you find 5 issues related to Qwen-3.5 on ggml-org/llama.cpp?

## Tool Calls
```log
2026-11-23 22:59:45,557 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Query sent to the model.
2026-11-23 22:59:46,375 | INFO     | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Input tok; 1011, Cached tok: 0
2026-11-23 22:59:46,375 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Executing tool calls...
2026-11-23 22:59:46,375 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool request: {"call_id": "fc_d8c0df92-54b7-4dc1-96c3-9bd6e5bf02bb", "tool": "github__search_issues", "arguments": "{\"fields\":[\"number\",\"title\",\"html_url\"],\"owner\":\"ggml-org\",\"page\":1,\"perPage\":10,\"query\":\"Qwen-3.5\",\"repo\":\"llama.cpp\"}"}
2026-11-23 22:59:48,806 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool result: {"call_id": "fc_d8c0df92-54b7-4dc1-96c3-9bd6e5bf02bb", "tool": "github__search_issues", "success": true, "error": null, "result_bytes": 1921}
2026-11-23 22:59:48,806 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Query sent to the model.
2026-11-23 22:59:49,649 | INFO     | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Input tok; 1694, Cached tok: 0
2026-11-23 22:59:49,649 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Executing tool calls...
2026-11-23 22:59:49,649 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool request: {"call_id": "fc_94d2a873-80ed-4027-abe4-94ed025f4492", "tool": "github__search_issues", "arguments": "{\"fields\":[\"number\",\"title\",\"html_url\"],\"owner\":\"ggml-org\",\"page\":1,\"perPage\":20,\"query\":\"Qwen 3.5\",\"repo\":\"llama.cpp\"}"}
2026-11-23 22:59:52,246 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool result: {"call_id": "fc_94d2a873-80ed-4027-abe4-94ed025f4492", "tool": "github__search_issues", "success": true, "error": null, "result_bytes": 3781}
2026-11-23 22:59:52,246 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Query sent to the model.
2026-11-23 22:59:53,493 | INFO     | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Input tok; 2963, Cached tok: 0
2026-11-23 22:59:53,494 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Executing tool calls...
2026-11-23 22:59:53,494 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool request: {"call_id": "fc_16b86244-a96e-4bde-aa8b-8664762b81e5", "tool": "github__search_issues", "arguments": "{\"fields\":[\"number\",\"title\",\"html_url\"],\"owner\":\"ggml-org\",\"page\":1,\"perPage\":20,\"query\":\"3.5\",\"repo\":\"llama.cpp\"}"}
2026-11-23 22:59:55,376 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool result: {"call_id": "fc_16b86244-a96e-4bde-aa8b-8664762b81e5", "tool": "github__search_issues", "success": true, "error": null, "result_bytes": 120}
2026-11-23 22:59:55,376 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Query sent to the model.
2026-11-23 22:59:55,376 | DEBUG    | 6cd8ff3787b1463cad6110028ea17da4 | app.126866840715136.application | Tool-turn budget exhausted (3); requesting final summary.
```

## LLM Response 1
Below are five issues from the **ggml‑org/llama.cpp** repository that are related—either directly or loosely—to the Qwen‑3.5 model family. All of the issue numbers, titles, and URLs come from the search results that were already retrieved (no additional tools were used).

| # | Issue (title) | Relation to Qwen‑3.5 | URL |
|---|---------------|----------------------|-----|
| **29145** | **“Qwen 3.5 MTP fails to load compact draft vocabularies (missing d2t mapping support)”** | Directly mentions *Qwen 3.5* and reports a loading problem. | <https://github.com/ggml-org/llama.cpp/issues/29145> |
| **29513** | **“Qwen3.5‑4B: first request after load is extremely slow (CUDA backend), warm performance is fine (RTX 2060 / sm_75, b11206)”** | Directly mentions *Qwen3.5‑4B* and describes a performance issue. | <https://github.com/ggml-org/llama.cpp/issues/29513> |
| **31551** | **“llama : add dense FFN support for Qwen3Next (Qwen3.5/3.8‑27B dense) and fix SIGFPE when n_expert_used == 0”** | The title explicitly includes “Qwen3.5” (as part of the Qwen3Next family) and discusses a feature/bug fix. | <https://github.com/ggml-org/llama.cpp/issues/31551> |
| **30605** | **“Qwen3 embeddings with bidirectional attention and an output projection”** | Does not contain “3.5” in the title, but it is about Qwen‑3 model embeddings, which are closely related to the Qwen‑3.5 family. (Loose match) | <https://github.com/ggml-org/llama.cpp/issues/30605> |
| **32127** | **“Feature Request: Support Qwen3‑ForcedAligner‑0.6B”** | Again, the title mentions a Qwen‑3 variant (not 3.5 specifically) and requests support for a related component. (Loose match) | <https://github.com/ggml-org/llama.cpp/issues/32127> |

### How the evidence supports the answer
* The search for “Qwen‑3.5” returned a list of issues that include numbers 29145, 29513, 31551, 30605, and 32127 (see the second‑search result)【tool】.  
* Issues 29145, 29513, and 31551 explicitly name **Qwen 3.5** in their titles, satisfying the request for “issues related to Qwen‑3.5”.  
* Issues 30605 and 32127 do not mention “3.5” but are about the broader Qwen‑3 family; according to the guidelines, they are presented as **loose** matches.

### Uncertainties / Open points
* The two “loose” entries (#30605, #32127) are not strictly about Qwen‑3.5, so if only exact “3.5” mentions are required, additional exact matches would need to be located (which is not possible now because the tool budget is exhausted).  
* No status (open/closed) information is available in the retrieved data, so the current state of each issue cannot be confirmed.  

**In summary:** the five issues listed above are the best matches for “Qwen‑3.5” based on the evidence already gathered.

## User Message 2
explain the first one to me

## Tool Calls
```log
2026-11-23 23:01:10,615 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Query sent to the model.
2026-11-23 23:01:11,622 | INFO     | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Input tok; 4864, Cached tok: 0
2026-11-23 23:01:11,623 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Executing tool calls...
2026-11-23 23:01:11,623 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Tool request: {"call_id": "fc_7c22a7d4-87c6-42b5-aed3-0ce505dc1e46", "tool": "github__issue_read", "arguments": "{\"issue_number\":29145,\"method\":\"get\",\"owner\":\"ggml-org\",\"repo\":\"llama.cpp\"}"}
2026-11-23 23:01:13,581 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Tool result: {"call_id": "fc_7c22a7d4-87c6-42b5-aed3-0ce505dc1e46", "tool": "github__issue_read", "success": true, "error": null, "result_bytes": 2653}
2026-11-23 23:01:13,581 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Query sent to the model.
2026-11-23 23:01:59,389 | INFO     | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Input tok; 5712, Cached tok: 0
2026-11-23 23:01:59,389 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Executing tool calls...
2026-11-23 23:01:59,389 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Tool request: {"call_id": "fc_1c3d64a8-fa45-4476-9084-7b3cf7879aaa", "tool": "github__issue_read", "arguments": "{\"issue_number\":29145,\"method\":\"get_comments\",\"owner\":\"ggml-org\",\"page\":1,\"perPage\":20,\"repo\":\"llama.cpp\"}"}
2026-11-23 23:02:01,275 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Tool result: {"call_id": "fc_1c3d64a8-fa45-4476-9084-7b3cf7879aaa", "tool": "github__issue_read", "success": true, "error": null, "result_bytes": 714}
2026-11-23 23:02:01,275 | DEBUG    | 799d15c5631e4883b3421ecef0b892d8 | app.126866840715136.application | Query sent to the model.
```

## LLM Response 2
**Issue #29145 – “Qwen 3.5 MTP fails to load compact draft vocabularies (missing d2t mapping support)”**

**What the reporter observed**  
* When using Multi‑Token Prediction (MTP) speculative decoding with a *compact* draft vocabulary (e.g., a trimmed vocab used by FastMTP that relies on a `d2t` – draft‑to‑target – mapping tensor), the Qwen 3.5 model loaders (`llama_model_qwen35` and `llama_model_qwen35moe`) crash or abort during model loading or graph evaluation.  

**Root‑cause analysis (from the issue description)**  

| # | Problem | Explanation |
|---|---------|-------------|
| **1. Dimension mismatch in the loader** | The draft language‑model head (`output.weight` or `layer.nextn.shared_head_head`) is stored with dimensions `[n_embd, n_draft_vocab]` (e.g., 32 768 tokens). The loader code in `src/models/qwen35.cpp` and `src/models/qwen35moe.cpp` **always expects the full vocab size** (`n_vocab = 152 064`). This mismatch triggers an assertion failure or a crash. |
| **2. Incorrect fallback path** | When the `output` tensor is `NULL`, the code falls back to duplicating the full‑vocab token‑embedding tensor (`LLM_TENSOR_TOKEN_EMBD`) using the *full* `n_vocab`. This overwrites the compact draft head, again breaking the model. |
| **3. Missing logits scattering** | Other model implementations (e.g., `dflash.cpp`, `eagle3.cpp`) scatter the draft‑candidate logits onto a full‑size target‑logits canvas (filling missing entries with `‑inf`) via `ggml_set_rows`. The Qwen 3.5 loaders lacked this step, so the draft logits never get correctly merged with the target logits. |

**How the issue was resolved**  

* The contributors (Sreesanth R and Allen Joseph) added a **single‑commit pull request** that:  
  * Adjusted the loader to respect the actual draft vocab size instead of assuming the full vocab.  
  * Fixed the fallback logic to correctly handle a missing `output` tensor without overwriting the compact head.  
  * Implemented the missing logits‑scatter step, mirroring the approach used in `dflash.cpp` and `eagle3.cpp`.  

* The fix was verified on **dual NVIDIA RTX PRO 6000 Ada/Blackwell GPUs**, achieving **102 – 114 tokens / second** (about a **2.3× speed‑up** over the broken version).  

**Outcome**  

* The issue was **closed** (state: *closed*, reason: *not_planned*) after the fix was merged via PR [#29143](https://github.com/ggml-org/llama.cpp/pull/29143).  
* A bot comment notes that the issue was closed because it had been inactive for 14 days after being marked stale.  

**Key take‑aways**  

1. **Model loaders must use the actual vocab size** of the draft model; hard‑coding the full vocab leads to crashes for trimmed vocabularies.  
2. **Fallback paths should not overwrite specialized tensors**; proper handling of `NULL` tensors is essential.  
3. **Logits from draft models need to be scattered onto the full‑size target canvas** to work with speculative decoding pipelines like MTP.  

**References**  
* Issue details (description, state, PR link) – https://github.com/ggml-org/llama.cpp/issues/29145【tool】  
* Bot comment indicating closure – https://github.com/ggml-org/llama.cpp/issues/29145#issuecomment-6783624350【tool】  

# A Simpler Task

## Sample Ask
can you summarize issue number 9026 in the github repo Stirling-Tools/Stirling-PDF

## Generated Response
**Issue #9026 – “Keep signer, reason and location on invisible certificate signatures”**  
(Repository: **Stirling‑Tools/Stirling‑PDF** – link: <https://github.com/Stirling-Tools/Stirling-PDF/pull/9026>)

| Item | Details |
|------|---------|
| **Type** | Pull‑request (treated as an “issue” in the repo’s issue tracker) |
| **Title** | “Keep signer, reason and location on invisible certificate signatures” |
| **State** | **Open** (as of the last fetch) |
| **Author** | @Frooodle |
| **Key Goals** | 1. Make the *Reason* and *Location* fields available for **invisible** PDF signatures, and have them be sent with the signature (they were previously only sent for visible signatures).<br>2. Revise the signature‑appearance UI: replace the old “Visible/Invisible” toggle with a “Show signature on page” switch, plus optional logo switch that appears only when a visible signature is chosen.<br>3. Move the *Reason*, *Location* and optional *Signer name* controls into a collapsed “Signature details (optional)” section.<br>4. Improve signature validation: when a signature has no `/Name`, the PDF‑signature‑validator now uses the certificate’s common name (e.g., “Stirling PDF Inc Server”) as the signer. This also allows a user‑supplied “Signer name” override for certificates whose names are unreadable. |
| **Implementation Highlights** | • Added new form controls for Reason, Location and Signer name.<br>• Updated the appearance editor to hide/show relevant fields based on the visibility toggle.<br>• Adjusted the backend signature‑validation logic to use the certificate’s CN when `/Name` is missing.<br>• Updated UI screenshots and a walkthrough HTML file (see `pr-9026-ui-walkthrough.html`). |
| **Testing & Validation** | • Verified that an invisible signature with Reason/Location but no signer name shows “Stirling PDF Inc Server” in the validation report.<br>• Confirmed that providing a custom signer name (“John A. Smith”) replaces the certificate CN in the report.<br>• Both signatures were verified as trusted.<br>• The visible‑mode layout was checked to ensure re‑signing did not occur after the new switch was changed.<br>• Ran `task frontend:check` and `task backend:check` to confirm no new linting or type‑checking errors. |
| **Checklist Status** | All required checklist items (code review, linting, documentation updates, UI screenshots, testing) are marked “✓” in the PR’s body. |
| **Additional Resources** | • UI walkthrough: <https://github.com/user-attachments/files/35286211/pr-9026-ui-walkthrough.html> |
| **Note on Data** | The API response was truncated; only the relevant summary information is shown above. The issue remains open as of this snapshot. |

**Bottom line:** Issue #9026 introduces full support for Reason, Location, and optional signer name on **invisible** PDF signatures, refactors the signature‑appearance UI for clarity, and improves validation logic so that invisible signatures still carry meaningful metadata.