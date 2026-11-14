# harness/llms

## Purpose
- Synchronous, non-streaming, text-only client for OpenAI-compatible Chat Completions.

## Public interface
- `from harness.llms import SyncTextLLMClient`.
- `SyncTextLLMClient(model: str | None = None, api_key: str | None = None, provider_url: str | None = None) -> None`.
- `client.model: str` selects the model for generation and can be reassigned.
- `client.check_connection()` returns the provider's model listing; no return annotation.
- `client.generate_next(tools: list[ChatCompletionToolParam], messages: list[ChatCompletionMessageParam], *, dangerously_ignore_usage: bool = False) -> tuple[ChatCompletion, int, int]`.
- `sync_client.guarded_execution[**P, R](func: Callable[P, R]) -> Callable[P, R]`: decorator that translates common OpenAI SDK errors into `harness.exceptions` types and preserves the wrapped signature. Internal to the client; don't use it outside this package unless asked.

## Contracts
- Constructor arguments override environment values; only `None` falls back to `MODEL`, `API_KEY`, or `MODEL_URL`, respectively.
- Missing required environment values raise `harness.exceptions.EnvVarNotSetError`.
- Callers supply OpenAI message and tool parameter lists; generation sends them with automatic tool choice.
- Generation returns the full completion, total prompt tokens, and cached prompt tokens (zero when cache details are absent).
- Missing usage raises `UnexpectedResponseError`; `dangerously_ignore_usage=True` returns the completion with both counts zero.
- Connection checks and generation make provider requests and translate common SDK errors (authentication, rate limit, timeout, connection, other status errors) into `InvalidAPIKeyError`, `RateLimitedError`, `TimeoutError`, `ConnectionError`, and `UnexpectedResponseError` from `harness.exceptions`.
- SDK errors not covered by the decorator propagate unchanged.
- Translated errors retain the original exception as their cause.

## Dependencies
- `harness.helpers.load_env` for configuration.
- `harness.exceptions` for framework errors.
- `harness.PKG_ROOT_DIR` (set in the root `harness/__init__.py`) is the base for all path resolution. Derive paths from it; never from the working directory.
- Within `harness`, depend only on `helpers` and `exceptions`. Ask before importing any other harness package.

## Testing
- No automated tests for this package. Don't add tests that hit a real provider.

## Gotchas
- `harness.exceptions.TimeoutError` and `ConnectionError` shadow the Python builtins. Always import them explicitly from `harness.exceptions`; never catch or raise the builtins in framework code.
- `check_connection()` lists models; it does not check whether the configured model can generate completions.
- The second returned count is prompt tokens, not completion tokens; cached tokens are returned separately.
- Constructor errors are outside the SDK error translation decorator.
- Raise only exceptions from `harness/exceptions.py`. If one is missing, ask before adding it.

## Known issues
- `check_connection()` has no return annotation.