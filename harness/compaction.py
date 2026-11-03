import json

from typing import cast
from openai.types.chat import ChatCompletionMessageParam
from .prompts import PromptStore
from .enums import PromptFamily
from .llms import SyncTextLLMClient

def naive_compaction(
    messages: list[ChatCompletionMessageParam],
    llm_client: SyncTextLLMClient,
    recent_turns_to_keep: int,
) -> list[ChatCompletionMessageParam]:
    """
    Performs naive compaction by summarizing earlier message blocks. It ensures proper tool call
    loop boundaries when compacting. However, it is not aware of any factual / critical information
    to be saved. Hence, it maybe lossy and quality is dependent on the model itself.
    """

    user_indices = [
        i for i, message in enumerate(messages) if message["role"] == "user"
    ]

    if len(user_indices) <= recent_turns_to_keep:
        return messages
    
    # start of the oldest user turn that needs to be preserved
    compact_until = user_indices[-recent_turns_to_keep]

    # As the context window fills up and gets compacted model will only have a rough idea of the
    # oldest messages and tool calls. Hence, this compaction strategy must be called less frequently
    # and should be accompanied by a higher recent_turns_to_keep which in turn is set via a higher
    # compaction threshold.
    old_history = messages[1:compact_until]    # Gets compacted (summarized)
    recent_history = messages[compact_until:]  # Remains safe to maintain the recent context

    if not old_history:
        return messages

    response, _, _ = llm_client.generate_next([], cast(list[ChatCompletionMessageParam], [
        {
            "role": "system",
            "content": PromptStore.load_prompt(PromptFamily.COMPACTION),
        },
        {
            "role": "user",
            "content": json.dumps(old_history, ensure_ascii=False),
        },
    ]))

    summary = response.choices[0].message.content

    if not summary:
        return messages
    
    return cast(list[ChatCompletionMessageParam], [
        messages[0],  # System Prompt
        {
            "role": "system",
            "content": ("Summary of earlier conversation:\n" + summary), # Summary
        },
        *recent_history, # Recent History to preserve immediate context
    ])