from functools import wraps
from collections.abc import Callable
from typing import Any
from pathlib import Path

import openai
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from ..helpers import load_env
from .. import exceptions, PKG_ROOT_DIR

def guarded_execution(func: Callable[..., Any]) -> Callable[..., Any]:
    
    source_file = Path(func.__code__.co_filename)

    try:
        relative_path = source_file.resolve().relative_to(PKG_ROOT_DIR.parent)
    except ValueError:
        relative_path = Path(source_file.name)

    source = (
        f"{func.__qualname__} "
        f"({relative_path}:{func.__code__.co_firstlineno})"        
    )
    
    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return func(self, *args, **kwargs)

        except openai.AuthenticationError as exc:
            raise exceptions.InvalidAPIKeyError(source) from exc

        except openai.RateLimitError as exc:
            raise exceptions.RateLimitedError(source) from exc

        except openai.APITimeoutError as exc:
            raise exceptions.TimeoutError(source) from exc

        except openai.APIConnectionError as exc:
            raise exceptions.ConnectionError(source) from exc

        except openai.APIStatusError as exc:
            raise exceptions.UnexpectedResponseError(
                source,
                f"Status code: {exc.status_code}, Message: {exc.message}"
            ) from exc
    return wrapper


class SyncTextLLMClient:
    """ Synchronous, non streaming, text-only OpenAI Compatible LLM Client. """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        provider_url: str | None = None,
    ) -> None:
        
        self.model: str = model if model is not None else load_env("MODEL")

        api_key = api_key if api_key is not None else load_env("API_KEY")
        provider_url = provider_url if provider_url is not None else load_env("MODEL_URL")

        self.__client: openai.OpenAI = openai.OpenAI(base_url=provider_url, api_key=api_key)

    @guarded_execution
    def check_connection(self):
        """ Would throw InvalidAPIKeyError if it fails """
        return self.__client.models.list()

    @guarded_execution
    def generate_next(
        self,
        tools: list[ChatCompletionToolParam],
        messages: list[ChatCompletionMessageParam],
        *,
        dangerously_ignore_usage: bool = False,
    ) -> tuple[ChatCompletion, int, int]:
        """ Generates the next message in the message list provided """

        response = self.__client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        
        usage = response.usage
        details = usage.prompt_tokens_details if usage else None

        if not usage or not details:
            if not dangerously_ignore_usage:
                raise exceptions.UnexpectedResponseError(
                    self.__class__.__qualname__, "Usage statistics not present in response"
                )

        return (
            response,
            usage.prompt_tokens if usage else 0,
            details.cached_tokens or 0 if details else 0
        )