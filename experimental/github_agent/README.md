# GitHub issue agent

Ask about a known GitHub issue by URL or by owner, repository, and issue number.
The agent uses the hosted GitHub MCP server's `issue_read` tool for issue details
and comments.

Set `GITHUB_TOKEN` to a personal access token with read access to the target
repository's issues. Set `MODEL`, `MODEL_URL`, and `API_KEY` for a Chat Completions
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
2026-11-23 22:27:19,306 | DEBUG    | 09d45313d68b4c82a8c05d2f04149f79 | app.124508680649856.application | Query sent to the model.
2026-11-23 22:27:20,177 | INFO     | 09d45313d68b4c82a8c05d2f04149f79 | app.124508680649856.application | Input tok; 971, Cached tok: 0
2026-11-23 22:27:20,177 | DEBUG    | 09d45313d68b4c82a8c05d2f04149f79 | app.124508680649856.application | Executing tool calls...
2026-11-23 22:27:20,177 | DEBUG    | 09d45313d68b4c82a8c05d2f04149f79 | app.124508680649856.application | Tool request: {"call_id": "fc_8b1288e9-1432-4c21-9ac6-8e6171d530e6", "tool": "github__search_issues", "arguments": "{\"fields\":[\"number\",\"title\",\"html_url\"],\"owner\":\"ggml-org\",\"perPage\":5,\"query\":\"Qwen-3.5\",\"repo\":\"llama.cpp\"}"}
2026-11-23 22:27:22,795 | DEBUG    | 09d45313d68b4c82a8c05d2f04149f79 | app.124508680649856.application | Tool result: {"call_id": "fc_8b1288e9-1432-4c21-9ac6-8e6171d530e6", "tool": "github__search_issues", "success": true, "error": null, "result_bytes": 936}
2026-11-23 22:27:22,795 | DEBUG    | 09d45313d68b4c82a8c05d2f04149f79 | app.124508680649856.application | Query sent to the model.
```

## LLM Response 1
Here are five issues on **ggml-org/llama.cpp** that mention or relate to **Qwen‑3.5**:

| Issue # | Title | Link |
|---------|-------|------|
| **31072** | *Get ready for qwen4* | [https://github.com/ggml-org/llama.cpp/issues/31072](https://github.com/ggml-org/llama.cpp/issues/31072) |
| **31796** | *Qwen2.5‑Omni audio: clips are padded to 30 s and the encoder does not use 2 s windows* | [https://github.com/ggml-org/llama.cpp/issues/31796](https://github.com/ggml-org/llama.cpp/issues/31796) |
| **32127** | *Feature Request: Support Qwen3‑ForcedAligner‑0.6B* | [https://github.com/ggml-org/llama.cpp/issues/32127](https://github.com/ggml-org/llama.cpp/issues/32127) |
| **30605** | *Qwen3 embeddings with bidirectional attention and an output projection* | [https://github.com/ggml-org/llama.cpp/issues/30605](https://github.com/ggml-org/llama.cpp/issues/30605) |
| **29145** | *Qwen 3.5 MTP fails to load compact draft vocabularies (missing d2t mapping support)* | [https://github.com/ggml-org/llama.cpp/issues/29145](https://github.com/ggml-org/llama.cpp/issues/29145) |

*All results were retrieved from the GitHub issue search for the query “Qwen‑3.5” in the `ggml-org/llama.cpp` repository.*

## User Message 2
explain the first one to me

## Tool Calls
```log
2026-11-23 22:27:59,381 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Query sent to the model.
2026-11-23 22:28:00,085 | INFO     | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Input tok; 1787, Cached tok: 0
2026-11-23 22:28:00,085 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Executing tool calls...
2026-11-23 22:28:00,085 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Tool request: {"call_id": "fc_e2067f0b-779c-4e91-ade7-60edb7763e23", "tool": "github__issue_read", "arguments": "{\"issue_number\":31072,\"method\":\"get\",\"owner\":\"ggml-org\",\"repo\":\"llama.cpp\"}"}
2026-11-23 22:28:01,939 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Tool result: {"call_id": "fc_e2067f0b-779c-4e91-ade7-60edb7763e23", "tool": "github__issue_read", "success": true, "error": null, "result_bytes": 1456}
2026-11-23 22:28:01,939 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Query sent to the model.
2026-11-23 22:28:02,540 | INFO     | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Input tok; 2319, Cached tok: 0
2026-11-23 22:28:02,540 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Executing tool calls...
2026-11-23 22:28:02,540 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Tool request: {"call_id": "fc_906861b9-ef3d-4f4d-a082-aefbc5ce14be", "tool": "github__issue_read", "arguments": "{\"issue_number\":31072,\"method\":\"get_comments\",\"owner\":\"ggml-org\",\"repo\":\"llama.cpp\"}"}
2026-11-23 22:28:04,368 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Tool result: {"call_id": "fc_906861b9-ef3d-4f4d-a082-aefbc5ce14be", "tool": "github__issue_read", "success": true, "error": null, "result_bytes": 3279}
2026-11-23 22:28:04,368 | DEBUG    | 323c6bb0e3814d13b4f52203aabaa1b3 | app.124508680649856.application | Query sent to the model.
```

## LLM Response 2
**Issue #31072 – “Get ready for qwen4”**  
*Repository:* `ggml-org/llama.cpp`  
*Opened by:* user `0wwafa` on 24 Oct 2026  
*Status:* open (no pull‑request has closed it yet)  

---

### What the issue is about  
The issue is a **feature request** to add support for the upcoming **Qwen 4** model family (specifically the *Qwen4‑27B dense* variant).  
The author references a pull‑request in the `analytics-zoo/vllm-xpu-kernels` repository that introduces Intel XPU kernels for this model. Those kernels are the only concrete public details available at the time, so the issue explains why a separate implementation in llama.cpp is needed.

---

### Key points from the original post  
| Section | Summary |
|---------|---------|
| **Prerequisites** | The user has the latest llama.cpp code, has followed the README, checked that the issue isn’t duplicate, and has a new enhancement to propose. |
| **Feature Description** | Links to https://github.com/analytics-zoo/vllm-xpu-kernels/pull/22 and a brief note “PR for qwen 4”. |
| **Motivation** | “because.” – the post is a placeholder; the real motivation is to prepare the repository for the new Qwen4 architecture. |
| **Possible Implementation** | Just a period – the details are to be fleshed out. |
| **Labels** | `enhancement` – it’s a new feature request. |

---

### Comment from `adambenhassen` (Oct 24 2026)  
The comment provides a deep‑dive into what the referenced PR adds and what the Qwen 4 model looks like:

* **Architecture** – Qwen4‑27B is a dense variant of the Qwen3.8 backbone with new “Qwen4‑generation” features (hyper‑connections, gated output, local QSA, etc.).  
* **Comparison table** – lists hidden size, attention heads, gate type, FFN size, MTP layer count, etc., comparing Qwen3.8‑27B to the Qwen4‑27B kernel design.  
* **Evidence** – shows specific source files from the PR (`hc_dense_sycl.cpp`, `fp8_dense.cpp`, etc.) and the kernel tuning numbers.  
* **Unknowns** – points out missing details (layer count, QSA weights, Flash‑Next memory tables, etc.).  
* **Implications** – highlights that existing `qwen3_5` support will not load Qwen4, that inference engines will need new model code (hyper‑connections, indexer), that speculative‑decoding drafters will likely need retraining, and that activation memory per token will increase.

---

### Bottom line  

The issue is a call‑to‑action for the llama.cpp developers to **implement Qwen 4 support**. It references external kernel code that defines most of the architectural changes, but the implementation in llama.cpp is not yet present, and the issue remains open for discussion and development.

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