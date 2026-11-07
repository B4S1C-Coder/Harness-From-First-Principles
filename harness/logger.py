import logging
import queue
from contextlib import contextmanager
from contextvars import ContextVar, Token
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from collections.abc import Generator
from uuid import uuid4
from .helpers import load_env

class _CorrelationFilter(logging.Filter):
    def __init__(self, context: ContextVar[str]) -> None:
        super().__init__()
        self._context = context

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self._context.get()
        return True

class ApplicationLogger:
    def __init__(
        self,
        log_dir: str | Path = "logs",
        max_bytes: int | None = None,
        backup_count: int | None = None,
        console: bool = False,
    ) -> None:

        self._closed = False
        self._console = console

        max_bytes = max_bytes or load_env(
            "APP_LOGGER_MAX_BYTES", cast=int, default= 5 * 1024 * 1024
        )

        backup_count = backup_count or load_env("APP_BACKUP_COUNT", cast=int, default=3)

        self._correlation_id: ContextVar[str] = ContextVar(
            f"correlation_id_{uuid4().hex}", default="-"
        )

        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(correlation_id)s | %(name)s | %(message)s"
        )

        self._app_logger, self._app_listener = self._setup_logger(
            "application", self._log_dir / "application.log", max_bytes, backup_count, console
        )

        self._trace_logger, self._trace_listener = self._setup_logger(
            "traces", self._log_dir / "traces.log", max_bytes, backup_count, console
        )
    
    def _setup_logger(
        self,
        name: str,
        path: Path,
        max_bytes: int,
        backup_count: int,
        console: bool
    ) -> tuple[logging.Logger, QueueListener]:

        log_queue: queue.Queue[logging.LogRecord] = queue.Queue()

        file_handler = RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(self._formatter)

        queue_handler = QueueHandler(log_queue)
        queue_handler.addFilter(
            _CorrelationFilter(self._correlation_id)
        )

        logger = logging.getLogger(
            f"app.{id(self)}.{name}"
        )

        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.addHandler(queue_handler)

        handlers: list[logging.Handler] = [file_handler]
        
        if console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self._formatter)
            handlers.append(console_handler)

        listener = QueueListener(
            log_queue, *handlers, respect_handler_level=True
        )
        listener.start()

        return logger, listener

    @contextmanager
    def correlation_scope(self) -> Generator[str, None, None]:
        correlation_id = uuid4().hex
        token: Token[str] = self._correlation_id.set(correlation_id)

        try:
            yield correlation_id
        finally:
            self._correlation_id.reset(token)

    def debug(self, message: str, *args: object) -> None:
        self._app_logger.debug(message, *args)

    def info(self, message: str, *args: object) -> None:
        self._app_logger.info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        self._app_logger.warning(message, *args)

    def error(self, message: str, *args: object) -> None:
        self._app_logger.error(message, *args)

    def critical(self, message: str, *args: object) -> None:
        self._app_logger.critical(message, *args)

    def log_exception(self, message: str, exc: Exception, *, include_trace: bool = True) -> None:
        self._app_logger.error(
            "%s: %s: %s", message, type(exc).__name__, exc
        )

        if include_trace:
            self._trace_logger.error(
                "%s: %s: %s",
                message,
                type(exc).__name__,
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def close(self) -> None:
        # The tests call close() explicitly, as a result it'd get called twice.
        # So it must be idempotent.
        if self._closed:
            return

        self._closed = True

        self._app_listener.stop()
        self._trace_listener.stop()

        # Since _setup_logger() uses logging.getLogger() and Python's logging.getLogger()
        # maintains a global registry of logger instances. So even after ApplicationLogger instance
        # is destroyed, python might still retain the under lying logger instances and handlers.

        # So across tests, when new instances are created they might still have the data from
        # prior destroyed instances (due to above). So queue handlers must be detached from this
        # global registry as below
        for logger in (self._app_logger, self._trace_logger):
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()

        for listener in (self._app_listener, self._trace_listener):
            for handler in listener.handlers:
                handler.flush()
                handler.close()