"""Token estimation for deciding when to compact, without calling the provider.

`TokenEstimator` is hybrid. After any request the provider reports the exact prompt size, so the
estimate for the next request is that figure plus a tokenizer count of only the messages added
since. This keeps the error to the size of the delta instead of the whole conversation. Before the
first response there is no ground truth, so the whole request is counted and padded.

Install `tiktoken` to use the gpt-oss tokenizer (`o200k_harmony`). Without it, or if its
vocabulary cannot be loaded (first use downloads it), counting falls back to bytes per token.
"""

import json

from collections.abc import Sequence
from typing import Any


class TokenEstimator:
    PER_MESSAGE = 8  # harmony framing around each message; tune against logged actual counts
    FIRST_REQUEST_MARGIN = 1.15

    def __init__(
        self, encoding: str | None = "o200k_harmony", fallback_bytes_per_token: float = 2.5
    ) -> None:
        self._enc: Any = None
        if encoding is not None:
            try:
                import tiktoken

                self._enc = tiktoken.get_encoding(encoding)
            except Exception:  # not installed, unknown encoding, or vocab download failed
                self._enc = None
        self.fallback_bytes_per_token = fallback_bytes_per_token

    @property
    def has_tokenizer(self) -> bool:
        """False means counts come from the bytes-per-token fallback."""
        return self._enc is not None

    def count(self, text: str) -> int:
        if self._enc is None:
            return int(len(text.encode("utf-8")) / self.fallback_bytes_per_token) + 1
        # Logs may contain text like "<|endoftext|>", which tiktoken refuses by default.
        return len(self._enc.encode(text, disallowed_special=()))

    def message(self, message: Any) -> int:
        text = message.get("content") or ""
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        for call in message.get("tool_calls") or []:
            text += call["function"]["name"] + call["function"]["arguments"]
        text += message.get("reasoning") or ""  # counted only while reasoning stays in history
        return self.PER_MESSAGE + self.count(text)

    def next_request(
        self,
        messages: Sequence[Any],
        tools: Sequence[Any] | None = None,
        *,
        last_prompt_tokens: int | None = None,
        counted: int = 0,
    ) -> int:
        """Estimate the prompt tokens of the next request.

        `messages[:counted]` were already part of the request that reported `last_prompt_tokens`.
        """
        if last_prompt_tokens is None:
            base = self.count(json.dumps(tools, ensure_ascii=False)) if tools else 0
            base += sum(self.message(m) for m in messages)
            return int(base * self.FIRST_REQUEST_MARGIN)
        return last_prompt_tokens + sum(self.message(m) for m in messages[counted:])
