# Log investigation experiment

Keep evaluation code in `eval/`. It may import the experiment and public harness APIs.
Keep the interactive investigator and the framework independent of the evaluator.

- `run.investigate_turn(agent, query)` returns the final report and the number of assistant tool-call batches. `run.run_turn(agent, query, outputs)` also saves the interactive handoff.
- `eval.loader.load_jobs(root)` returns labeled jobs in manifest order. `workspace(job)` yields a temporary directory containing only that job's container logs. Keep the ground truth outside the investigator's input.
- `eval.runner.run_turn(agent, meter, query)` measures a single investigation. All clients supplied to the agent must share the same meter, including the SQL helper. Reuse the meter across jobs for pacing and build a new agent and SQLite backend for each job.
- `eval.runner.run_jobs(jobs, output, investigate, limit)` checkpoints completed reports and returns the number added. The callback receives only the isolated workspace. A failed turn propagates and remains eligible on resume.
- Windowed searches and nearby ordering use the most recent parsed timestamp in each file. Continuations retain null parsed fields. Empty keyword searches include `keyword_matches_all_logs`. Within one run, repeated model calls with identical arguments return a reference to the earlier result.
- The confusion matrix has prediction rows (including `unclassified`) and shipped-label columns. `eval.scorer.score(records)` uses the report to predict and the manifest label to evaluate. Keep report keyword rules in `eval/scorer.py`.

Use fake clients in tests. Run `uv run pytest tests/test_hadoop_eval.py tests/test_direct_log_agent.py tests/test_investigation_policy.py -v` for the evaluator and shared turn loop.
