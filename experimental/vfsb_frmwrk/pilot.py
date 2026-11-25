"""Run the disk-full WordCount pilot with the framework investigator."""

from contextlib import closing

from dotenv import load_dotenv

from experimental.vfsb_subagent.eval.loader import load_jobs, workspace
from experimental.vfsb_subagent.eval.meter import Meter, MeteredClient
from experimental.vfsb_subagent.eval.scorer import classify
from harness.log.log_backend import SQLiteLogs
from harness.logger import ApplicationLogger
from .run import ROOT, build_agent, investigate_turn


def main() -> None:
    load_dotenv()
    data = ROOT / "data"
    jobs = load_jobs(data / "loghub_hadoop")
    job = next(job for job in jobs if job.id == "application_1445182159119_0002")
    prompt = (ROOT / "vfsb_subagent/system_main_agent.md").read_text(encoding="utf-8")
    meter = Meter()
    with workspace(job) as logs, closing(SQLiteLogs(logs)) as db:
        with closing(ApplicationLogger(data, console=True)) as logger:
            agent = build_agent(
                db,
                logger,
                MeteredClient("openai/gpt-oss-120b", meter),
                MeteredClient("openai/gpt-oss-20b", meter),
                prompt,
            )
            report, turns = investigate_turn(
                agent,
                "Investigate this Hadoop job. Did it run normally or is there evidence "
                "of a failure? Identify the most likely underlying issue, distinguish secondary "
                "symptoms, and cite specific timestamps and log lines. State any uncertainty.",
            )
            logger.info(
                "%s\n%s: predicted=%s expected=%s tool turns=%d",
                report,
                job.id,
                classify(report),
                job.label,
                turns,
            )


if __name__ == "__main__":
    main()
