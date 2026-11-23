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

## Complete Logs
```bash
uv run python -m experimental.github_agent.run
```


```bash
2026-11-23 21:52:49,806 | INFO     | - | app.128444188188864.application | github: kept 1 MCP tools (1498 definition bytes)
GitHub> can you summarize issue number 9026 in the github repo Stirling-Tools/Stirling-PDF
2026-11-23 21:53:32,596 | DEBUG    | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Query sent to the model.
2026-11-23 21:53:33,096 | INFO     | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Input tok; 470, Cached tok: 0
2026-11-23 21:53:33,096 | DEBUG    | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Executing tool calls...
2026-11-23 21:53:33,096 | DEBUG    | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Tool request: {"call_id": "fc_4f550b72-7aac-4001-8ebc-5fab76c299c0", "tool": "github__issue_read", "arguments": "{\"issue_number\":9026,\"method\":\"get\",\"owner\":\"Stirling-Tools\",\"repo\":\"Stirling-PDF\"}"}
2026-11-23 21:53:35,460 | DEBUG    | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Tool result: {"call_id": "fc_4f550b72-7aac-4001-8ebc-5fab76c299c0", "tool": "github__issue_read", "success": true, "error": null, "result_bytes": 4096}
2026-11-23 21:53:35,460 | DEBUG    | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Query sent to the model.
LLM Reply> **Issue #9026 – “Keep signer, reason and location on invisible certificate signatures”**  
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
2026-11-23 21:53:36,997 | INFO     | e9f438f154c041f0841973ebe405584e | app.128444188188864.application | Input tok; 1586, Cached tok: 0
GitHub> exit
```