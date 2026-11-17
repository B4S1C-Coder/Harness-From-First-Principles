from dotenv import load_dotenv
load_dotenv()
from harness.llms import SyncTextLLMClient

client = SyncTextLLMClient(model="openai/gpt-oss-20b")

msgs = [
    {"role": "system", "content": "You are concise."},
    {"role": "user", "content": "A train leaves at 3:40pm and the trip takes 2h 55m. When does it arrive? Think it through."},
]
resp, _, _ = client.generate_next([], msgs)
m = resp.choices[0].message

# 1) is the field there?
print("extra fields:", list((m.model_extra or {}).keys()))
reasoning = getattr(m, "reasoning", None)
print("reasoning present:", bool(reasoning), "| chars:", len(reasoning or ""))
print("usage:", resp.usage)  # look for reasoning tokens inside completion_tokens_details

# 2) what step() would store in history
stored = m.model_dump(exclude_none=True)
print("keys stored in history:", list(stored.keys()))

# 3) does a resent reasoning field count as input?
follow = {"role": "user", "content": "Now say that in one short sentence."}
_, tok_with, _ = client.generate_next([], [*msgs, stored, follow])
stripped = {k: v for k, v in stored.items() if k != "reasoning"}
_, tok_without, _ = client.generate_next([], [*msgs, stripped, follow])
print("prompt_tokens WITH reasoning resent   :", tok_with)
print("prompt_tokens WITHOUT reasoning resent:", tok_without)
