# TODO

- [ ] Standardize the synchronous LLM client hierarchy. Prefer using `SyncTextLLMClient` as the base for all synchronous clients, including `TextOnlyRetryClient`. Consider extracting a common synchronous base if the shared contract needs to be independent of the OpenAI client implementation.
