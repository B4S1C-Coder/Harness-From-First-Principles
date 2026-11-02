from pathlib import Path
from harness.logger import ApplicationLogger

def test_log_levels(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    app_logger.debug("Debug message")
    app_logger.info("Info message")
    app_logger.warning("Warning message")
    app_logger.error("Error message")
    app_logger.critical("Critical message")

    app_logger.close()

    content = (log_dir / "application.log").read_text(encoding="utf-8")

    assert "DEBUG" in content
    assert "INFO" in content
    assert "WARNING" in content
    assert "ERROR" in content
    assert "CRITICAL" in content

def test_correlation_id_is_attached_to_logs(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    with app_logger.correlation_scope() as correlation_id:
        app_logger.info("Inside correlation scope")

    app_logger.close()

    content = (log_dir / "application.log").read_text(encoding="utf-8")

    assert correlation_id in content
    assert "Inside correlation scope" in content

def test_correlation_id_resets_after_scope(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    app_logger.info("Before scope")

    with app_logger.correlation_scope() as correlation_id:
        app_logger.info("Inside scope")

    app_logger.info("After scope")
    app_logger.close()

    content = (log_dir / "application.log").read_text(encoding="utf-8")

    before, inside, after = [
        next(line for line in content.splitlines() if message in line)
        for message in ("Before scope", "Inside scope", "After scope")
    ]

    assert " | - | " in before
    assert f" | {correlation_id} | " in inside
    assert " | - | " in after

def test_nested_correlation_scopes(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    with app_logger.correlation_scope() as outer_id:
        app_logger.info("Outer before")

        with app_logger.correlation_scope() as inner_id:
            app_logger.info("Inner")

        app_logger.info("Outer after")

    app_logger.close()

    content = (log_dir / "application.log").read_text(encoding="utf-8")

    assert outer_id != inner_id

    outer_before = next(
        line for line in content.splitlines()
        if "Outer before" in line
    )

    inner = next(
        line for line in content.splitlines()
        if "Inner" in line
    )

    outer_after = next(
        line for line in content.splitlines()
        if "Outer after" in line
    )

    assert outer_id in outer_before
    assert inner_id in inner
    assert outer_id in outer_after

def test_exception_is_logged(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    try:
        raise ValueError("Something went wrong")
    except ValueError as exc:
        app_logger.log_exception("Test failure", exc)

    app_logger.close()

    app_content = (log_dir / "application.log").read_text(encoding="utf-8")
    trace_content = (log_dir / "traces.log").read_text(encoding="utf-8")

    assert "Test failure" in app_content
    assert "ValueError" in app_content
    assert "Something went wrong" in app_content

    assert "ValueError" in trace_content
    assert "Something went wrong" in trace_content
    assert "Traceback (most recent call last)" in trace_content

def test_exception_without_trace(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    try:
        raise RuntimeError("Expected failure")
    except RuntimeError as exc:
        app_logger.log_exception("Expected operation failure", exc, include_trace=False)

    app_logger.close()

    app_content = (log_dir / "application.log").read_text(encoding="utf-8")
    trace_content = (log_dir / "traces.log").read_text(encoding="utf-8")

    assert "Expected operation failure" in app_content
    assert  "RuntimeError" in app_content

    assert "Expected failure" not in trace_content
    assert "Traceback" not in trace_content

def test_log_files_are_created(
    app_logger: ApplicationLogger,
    log_dir: Path,
) -> None:

    assert (log_dir / "application.log").exists()
    assert (log_dir / "traces.log").exists()

def test_logging_instance_can_be_injected(
    app_logger: ApplicationLogger,
) -> None:

    class DummyService:
        def __init__(self, logger: ApplicationLogger) -> None:
            self.logger = logger

    service = DummyService(app_logger)
    assert service.logger is app_logger