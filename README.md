# Harness from First Principles
A harness being built from first principles to understand what even is an harness. The [`harness/`](./harness/) folder contains the harness (from first principles) as a framework. The harness is being made incrementally by introducing new features whilst addressing any shortcomings in the existing ones. So it's best to make this as a reusable framework as opposed to a task specific harness.

## Making a Basic Agent
An example of a very simple and naive agent using the framework. Note that below are just the useful snippets. See the complete examples in the [relevant examples folder](./examples/basic_agent/).

```python
class BasicAgent(SynchronousAgentBase):
    def handle_message(self, message: ChatCompletionMessage) -> bool:
        content = message.content

        if not content:
            raise UnexpectedResponseError(
                self.__class__.__qualname__, "Empty LLM response"
            )

        print(f"LLM Reply> {content}")

        # For normal messages end the turn
        return False

    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        self.logger.debug("Executing tool calls...")

        for tool_call in message.tool_calls or []:

            if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                self.logger.warning("Unsupported tool call skipped")
                continue

            self.logger.debug(f"Executing tool call: {tool_call.function.name}")

            result = ToolRegistry.execute(
                tool_call.function.name, json.loads(tool_call.function.arguments)
            )

            self.messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

        # For tool calls continue the turn (LLM gets multiple chances to run tools)
        return True
```

Running it is as simple as:
```python
agent = BasicAgent(
    client=SyncTextLLMClient(),
    logger=logger,
    tools=tools,
    system_prompt=PromptStore.load_prompt(PromptFamily.SYSTEM)
)

try:
    while True:
        query = input().strip()

        if query.lower() in ("exit", "quit"):
            break

        if not query:
            continue

        with agent.turn():
            agent.add_user_message(query)

            # step returns whether current turn should continue or not
            # you can add extra (in between turn) logic here, like determining
            # if the agent is in correct direction or not etc. or in a
            # master agent governing a sub agent secanrio.
            while agent.step():

                # For this simple example we do nothing.
                pass

finally:
    logger.close()
```

## Demo Run Output
```bash
uv run python -m examples.basic_agent.run
```

```log
2026-11-07 13:01:39,648 | DEBUG    | a10089293cb94bc0b8de3da16f20f7f7 | app.128280563737728.application | Query sent to the model.
LLM Reply> Got it! Your project **Atlas** uses Spring Boot, PostgreSQL, and Docker. I’ll keep that in mind for future questions.
2026-11-07 13:01:40,438 | INFO     | a10089293cb94bc0b8de3da16f20f7f7 | app.128280563737728.application | Input tok; 343, Cached tok: 0
2026-11-07 13:01:40,439 | DEBUG    | aadd4fcce0a54562920baea3f03608d7 | app.128280563737728.application | Query sent to the model.
2026-11-07 13:01:40,979 | INFO     | aadd4fcce0a54562920baea3f03608d7 | app.128280563737728.application | Input tok; 423, Cached tok: 0
2026-11-07 13:01:40,980 | DEBUG    | aadd4fcce0a54562920baea3f03608d7 | app.128280563737728.application | Executing tool calls...
2026-11-07 13:01:40,980 | DEBUG    | aadd4fcce0a54562920baea3f03608d7 | app.128280563737728.application | Executing tool call: get_weather
2026-11-07 13:01:40,980 | DEBUG    | aadd4fcce0a54562920baea3f03608d7 | app.128280563737728.application | Query sent to the model.
LLM Reply> **Patiala** – 28 °C, sunny.
2026-11-07 13:01:41,257 | INFO     | aadd4fcce0a54562920baea3f03608d7 | app.128280563737728.application | Input tok; 487, Cached tok: 0
2026-11-07 13:01:41,258 | DEBUG    | d38077c558604dc984ae4875664ffd02 | app.128280563737728.application | Query sent to the model.
LLM Reply> Understood—Atlas uses PostgreSQL.
2026-11-07 13:01:41,845 | INFO     | d38077c558604dc984ae4875664ffd02 | app.128280563737728.application | Input tok; 525, Cached tok: 256
2026-11-07 13:01:41,846 | DEBUG    | 500221cc7d244c5dbeb8c425c7d9e994 | app.128280563737728.application | Query sent to the model.
2026-11-07 13:01:42,397 | INFO     | 500221cc7d244c5dbeb8c425c7d9e994 | app.128280563737728.application | Input tok; 567, Cached tok: 0
2026-11-07 13:01:42,397 | DEBUG    | 500221cc7d244c5dbeb8c425c7d9e994 | app.128280563737728.application | Executing tool calls...
2026-11-07 13:01:42,397 | DEBUG    | 500221cc7d244c5dbeb8c425c7d9e994 | app.128280563737728.application | Executing tool call: list_directory
2026-11-07 13:01:42,397 | DEBUG    | 500221cc7d244c5dbeb8c425c7d9e994 | app.128280563737728.application | Query sent to the model.
LLM Reply> Contents of **/workspace/atlas**:

- `main.py`
- `helpers.py`
- `constants.py`
2026-11-07 13:01:43,058 | INFO     | 500221cc7d244c5dbeb8c425c7d9e994 | app.128280563737728.application | Input tok; 631, Cached tok: 0
2026-11-07 13:01:43,059 | DEBUG    | 3b20754f308442a2863ad22db49b2c93 | app.128280563737728.application | Query sent to the model.
LLM Reply> Got it—Atlas will use Flyway for database migrations.Noted! Atlas will use Flyway for its PostgreSQL migrations.
2026-11-07 13:01:43,332 | INFO     | 3b20754f308442a2863ad22db49b2c93 | app.128280563737728.application | Input tok; 684, Cached tok: 0
2026-11-07 13:01:43,332 | DEBUG    | 1ec4926df7b44b3c93199de985af2363 | app.128280563737728.application | Query sent to the model.
LLM Reply> - **Project name:** Atlas  
- **Database:** PostgreSQL  
- **Migration tool:** Flyway
2026-11-07 13:01:43,950 | INFO     | 1ec4926df7b44b3c93199de985af2363 | app.128280563737728.application | Input tok; 749, Cached tok: 0
2026-11-07 13:01:43,951 | DEBUG    | 7ec99ca5d481432ab6196361d6b49ff0 | app.128280563737728.application | Query sent to the model.
LLM Reply> Understood—**Orion** uses C++ and gRPC, separate from Atlas.
2026-11-07 13:01:44,617 | INFO     | 7ec99ca5d481432ab6196361d6b49ff0 | app.128280563737728.application | Input tok; 817, Cached tok: 0
2026-11-07 13:01:45,396 | DEBUG    | 815efca914b14ba2ac3bab069b9ab415 | app.128280563737728.application | Query sent to the model.
2026-11-07 13:01:45,685 | INFO     | 815efca914b14ba2ac3bab069b9ab415 | app.128280563737728.application | Input tok; 600, Cached tok: 0
2026-11-07 13:01:45,685 | DEBUG    | 815efca914b14ba2ac3bab069b9ab415 | app.128280563737728.application | Executing tool calls...
2026-11-07 13:01:45,685 | DEBUG    | 815efca914b14ba2ac3bab069b9ab415 | app.128280563737728.application | Executing tool call: get_weather
2026-11-07 13:01:45,686 | DEBUG    | 815efca914b14ba2ac3bab069b9ab415 | app.128280563737728.application | Query sent to the model.
LLM Reply> The current weather in Jaipur is **28 °C, sunny**.
2026-11-07 13:01:46,287 | INFO     | 815efca914b14ba2ac3bab069b9ab415 | app.128280563737728.application | Input tok; 646, Cached tok: 256
2026-11-07 13:01:46,288 | DEBUG    | 1f72184935164dcbbc159ae361934196 | app.128280563737728.application | Query sent to the model.
LLM Reply> **Atlas**  
- Language/stack: Spring Boot (Java)  
- Database: PostgreSQL  
- Migrations: Flyway  

**Orion**  
- Language: C++  
- Communication: gRPC  

No overlap between the two projects.
2026-11-07 13:01:46,639 | INFO     | 1f72184935164dcbbc159ae361934196 | app.128280563737728.application | Input tok; 691, Cached tok: 0
2026-11-07 13:01:46,639 | DEBUG    | 488d0866a76a40cda9758576ba0b743b | app.128280563737728.application | Query sent to the model.
LLM Reply> You first asked about the weather in **Patiala**.
2026-11-07 13:01:49,292 | INFO     | 488d0866a76a40cda9758576ba0b743b | app.128280563737728.application | Input tok; 774, Cached tok: 512
```