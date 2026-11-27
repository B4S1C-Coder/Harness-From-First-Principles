# RCA package contracts

Run the CLI with `python -m rca` and register missing prompt families with `python -m rca.prompts`. Registration preserves existing versions. Load settings through `RCAConfig.from_env()`.

`build_master(master_client, log_client, research_client, logger, mcp_tools, source, prompts, config)` returns a session-scoped SCMTT agent. `run_turn(agent, question)` returns its final text. Each log delegation builds a private InvestigationAgent over a finite LogSource snapshot. Specialist handoffs retain bounded findings in memory. All agent contexts use the shared 8,000-token budget.
