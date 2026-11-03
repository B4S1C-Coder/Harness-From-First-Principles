# Harness from First Principles

A harness being built from first principles to understand what even is an harness.

## Demo Run output
```bash
uv run python -m examples.basic_agent
```

```log
2026-11-04 03:27:33,146 | DEBUG    | 5ab5c82ba78047acb797c1b2b28eda4f | app.137784124465056.application | Query sent to model.
LLM Reply> Got it! Atlas is a Spring Boot project using PostgreSQL as its database and Docker for containerization. Let me know if you need anything specific for it.
2026-11-04 03:27:35,588 | INFO     | 5ab5c82ba78047acb797c1b2b28eda4f | app.137784124465056.application | Input tok: 343, Cached tok: 0
2026-11-04 03:27:35,588 | DEBUG    | d7117886888a4999b688b40897a63088 | app.137784124465056.application | Query sent to model.
2026-11-04 03:27:36,647 | INFO     | d7117886888a4999b688b40897a63088 | app.137784124465056.application | Input tok: 392, Cached tok: 0
2026-11-04 03:27:36,647 | DEBUG    | d7117886888a4999b688b40897a63088 | app.137784124465056.application | Executing tool calls ...
2026-11-04 03:27:36,647 | DEBUG    | d7117886888a4999b688b40897a63088 | app.137784124465056.application | Executing tool call: get_weather
2026-11-04 03:27:36,647 | DEBUG    | d7117886888a4999b688b40897a63088 | app.137784124465056.application | Query sent to model.
LLM Reply> **Patiala – Weather Forecast**

- **Temperature:** 28 °C  
- **Condition:** Sunny

Let me know if you’d like a more detailed forecast or anything else!
2026-11-04 03:27:37,283 | INFO     | d7117886888a4999b688b40897a63088 | app.137784124465056.application | Input tok: 456, Cached tok: 0
2026-11-04 03:27:37,284 | DEBUG    | f15cc7fe5bce49a2816d85ab6ce2c4f9 | app.137784124465056.application | Query sent to model.
LLM Reply> Understood—Atlas uses PostgreSQL.
2026-11-04 03:27:38,255 | INFO     | f15cc7fe5bce49a2816d85ab6ce2c4f9 | app.137784124465056.application | Input tok: 519, Cached tok: 0
2026-11-04 03:27:38,255 | DEBUG    | dbb3bb748a8a4321b5517b1dccade4e3 | app.137784124465056.application | Query sent to model.
2026-11-04 03:27:38,956 | INFO     | dbb3bb748a8a4321b5517b1dccade4e3 | app.137784124465056.application | Input tok: 546, Cached tok: 0
2026-11-04 03:27:38,956 | DEBUG    | dbb3bb748a8a4321b5517b1dccade4e3 | app.137784124465056.application | Executing tool calls ...
2026-11-04 03:27:38,956 | DEBUG    | dbb3bb748a8a4321b5517b1dccade4e3 | app.137784124465056.application | Executing tool call: list_directory
2026-11-04 03:27:38,956 | DEBUG    | dbb3bb748a8a4321b5517b1dccade4e3 | app.137784124465056.application | Query sent to model.
LLM Reply> Contents of `/workspace/atlas`:

- `main.py`
- `helpers.py`
- `constants.py`
2026-11-04 03:27:39,146 | INFO     | dbb3bb748a8a4321b5517b1dccade4e3 | app.137784124465056.application | Input tok: 610, Cached tok: 0
2026-11-04 03:27:39,146 | DEBUG    | ddc8c08695344c62a82107b32e35fa02 | app.137784124465056.application | Query sent to model.
LLM Reply> Got it—Atlas will use Flyway for database migrations.
2026-11-04 03:27:39,646 | INFO     | ddc8c08695344c62a82107b32e35fa02 | app.137784124465056.application | Input tok: 662, Cached tok: 0
2026-11-04 03:27:39,647 | DEBUG    | 9638764e5ee6481491a271ce1f412dd8 | app.137784124465056.application | Query sent to model.
LLM Reply> **Project name:** Atlas  
**Database:** PostgreSQL  
**Migration tool:** Flyway
2026-11-04 03:27:40,271 | INFO     | 9638764e5ee6481491a271ce1f412dd8 | app.137784124465056.application | Input tok: 700, Cached tok: 0
2026-11-04 03:27:40,272 | DEBUG    | 9c2f4ea6ae6c44f3b95e41638f642ec3 | app.137784124465056.application | Query sent to model.
LLM Reply> Understood. Orion is a separate project that uses C++ and gRPC. If you need details or help with either Atlas or Orion, justlet me know!
2026-11-04 03:27:39,448 | INFO     | 9c2f4ea6ae6c44f3b95e41638f642ec3 | app.137784124465056.application | Input tok: 749, Cached tok: 0
2026-11-04 03:27:39,448 | DEBUG    | da685f8382314a5894938867f3e925ed | app.137784124465056.application | Query sent to model.
2026-11-04 03:27:42,323 | INFO     | da685f8382314a5894938867f3e925ed | app.137784124465056.application | Input tok: 798, Cached tok: 0
2026-11-04 03:27:42,323 | DEBUG    | da685f8382314a5894938867f3e925ed | app.137784124465056.application | Executing tool calls ...
2026-11-04 03:27:42,324 | DEBUG    | da685f8382314a5894938867f3e925ed | app.137784124465056.application | Executing tool call: get_weather
2026-11-04 03:27:42,324 | DEBUG    | da685f8382314a5894938867f3e925ed | app.137784124465056.application | Query sent to model.
LLM Reply> **Jaipur – Weather Forecast**

- **Temperature:** 28 °C  
- **Condition:** Sunny
2026-11-04 03:27:43,209 | INFO     | da685f8382314a5894938867f3e925ed | app.137784124465056.application | Input tok: 854, Cached tok: 0
2026-11-04 03:27:44,844 | DEBUG    | 72687b09d92c41d6af4edb5fa9d43aab | app.137784124465056.application | Query sent to model.
LLM Reply> **Atlas (Spring Boot)**
- **Framework:** Spring Boot  
- **Database:** PostgreSQL (not MySQL)  
- **Containerization:** Docker  
- **Migrations:** Flyway  

**Orion (C++/gRPC)**
- Uses C++ as the primary language  
- Communication layer built with gRPC  

These are the key technical choices for each project.
2026-11-04 03:27:47,002 | INFO     | 72687b09d92c41d6af4edb5fa9d43aab | app.137784124465056.application | Input tok: 635, Cached tok: 256
2026-11-04 03:27:47,002 | DEBUG    | fb9fe8a80522468fb5cdf34c10bca7cb | app.137784124465056.application | Query sent to model.
LLM Reply> You first asked about the weather in **Patiala**.
2026-11-04 03:27:47,589 | INFO     | fb9fe8a80522468fb5cdf34c10bca7cb | app.137784124465056.application | Input tok: 736, Cached tok: 0
```