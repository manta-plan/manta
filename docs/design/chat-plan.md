# Prototype: LLM chat in Manta

## Status on 24 November 2026

Both steps are implemented on `sid/chat-docs-prototype`, in two commits that are not pushed: `a6b2d42` (step 1) and `81ffa71` (step 2). The sections from "Context" down are the plan as approved. This section and the next two record what happened.

| Part | State |
|---|---|
| Step 1, docs chat | Works locally, as you confirmed. |
| Step 2, SQL with a table | Implemented, off by default (`CHAT_SQL_ENABLED`). Not yet opened in a browser. |
| Backend unit tests (266), frontend tests (283), lint, type-check, build, strict docs build, pre-commit | Pass. |
| The model's SQL | Tested with a script against a record server on the host. See "Learnings". |
| Integration tests for both steps (`test_chat_route.py`) | Written, never run: Docker was off. |
| Backend image build with the new `docs` build context | Not run. |

Step 2 as built differs from the plan in four ways:

- **The `record` field holds names, not a catalogue name or zone levels.** The browser sends component types with their carriers, and attributes with unit, subject, and whether they are a series. The backend checks each name against a pattern and writes the text itself.
- **A record description over `CHAT_MAX_RECORD_CHARS` is cut, not refused.** A 422 would stop the docs chat too in a large project.
- **The description of the views is a prompt, not a docs page.** It is in `backend/src/manta/services/chat_prompts.py`, with four worked examples.
- **A reply that starts with a query and has no ```` ```sql ```` block also counts**, if it names a view. The 3B model sometimes leaves the block out.

## Learnings

### Models

- **`llama3.2:3b` answers docs questions well and fast enough.** The docs prompt is about 3,800 tokens. The first reply starts after 12–16 s, later ones after 1–4 s.
- **With the data prompt the request is about 5,100 tokens**, for the example record's input scenario (46 attributes, 2,100 characters of names). The first reply after a prompt change took 54–68 s, later ones 2–25 s. It fits the 8,192 budget with the history and reply limits unchanged.
- **The 3B model writes correct SQL for about half the data questions.** On 14 questions about `BEL-pre-aggregated-incl-patches-incl-results` (input scenario):

  | Outcome | Queries |
  |---|---|
  | Correct | 8 |
  | Ran, with a wrong result | 4 |
  | Failed, also after the retry | 2 |

- **A query that runs with a wrong result is the main risk.** Examples: the solar capacity divided by 1,000 under a column named `_mw`, and `p_nom` averaged as "efficiency". Nothing in the drawer marks these, so the greeting and the README tell the user to read the query.
- **Examples help more than description.** With one example the model got 3 of 8 right and reused `attributes.p_nom` for everything. Four examples (a sum, a top-N, a series, a plain count) fixed most of that.
- **The retry seldom helps a 3B model.** It recovered none of the failed queries in the last run.
- **The model picks the right kind of answer.** All 14 data questions got a query, and the 3 docs questions got text. One docs answer was wrong with the longer prompt ("What does the Inspect stage show?"), which is one data point.
- **`qwen3.5:2b` and `qwen3.5:4b` did not answer within 5 minutes on this laptop**, with memory at 10% free and swap nearly full. I did not diagnose it further and removed both models.
- **No hosted model was tested.** I had no API key for one. This is the open question for step 2.
- **Prompt injection works on the 3B model** (it wrote the poem). The design assumes that.
- **The model repeats the formatting it reads.** Bold markers in the docs came back in replies, so the backend strips them from the prompt.

### This machine

- **The Docker stack and a model do not fit together comfortably in 8 GB.** Docker's VM takes 3.8 GB. The integration tests plus a model load ran the machine out of memory, and you stopped Docker.
- **The record server runs on the host without Docker**, which is enough to test SQL:
  - In `docker/quack-server`: `uv run python -c "import duckdb; [duckdb.sql(f'INSTALL {e}') for e in ('quack', 'httpfs', 'json')]"`, once.
  - Then `QUACK_TOKEN=devtoken DEFAULT_RECORD=BEL-pre-aggregated-incl-patches-incl-results uv run uvicorn app.main:app --port 8010`.
  - I left two example stores (15 MB) in `docker/quack-server/data/records`, which is git-ignored. Delete the folder's contents if you do not want them.
- **Ollama's OpenAI-compatible route cannot set the context size**, and Ollama cuts a longer prompt off without an error. Hence the `manta-chat` model with `num_ctx 8192`.

### Code

- **A limit that must answer 422 or 429 has to be a dependency.** Inside the generator the response has already started with a 200.
- **A service must not import a route's request model.** Importing `chat_service` first failed with a circular import, so the service takes plain dicts.
- **FastAPI's built-in SSE works from a synchronous generator route**, so the chat needed no exception to the sync rule.
- **A scenario has values for 46 of the manifest's 153 attributes** (65 in a run result). `manta.attribute_summary` lists them, which keeps the record description small.
- **The views are harder than the prompt admits.** `snapshot` and `connection` are structs, `p` is per connection, and energy over a year needs the snapshot weights. The prompt covers none of these, so questions about dispatch or generation will fail.
- **The record server answers "Authorization failed" to SQL it cannot parse.** That error tells the model nothing useful on the retry.
- **"Select New run on the Run tab." starts like a query.** The unfenced fallback now requires a view name.

## Remaining steps

### To finish the prototype

1. **Open step 2 in a browser.** Start the stack with the `temporary-quack-setup` profile, set `CHAT_SQL_ENABLED=true` beside the three chat settings, and check:
   - A data question shows a table, with the query under "Query".
   - A failing query shows "Trying once more…", then a table or the error.
   - A docs question still gets a text answer.
   - After switching to a run result, a question about `p_nom_opt` reads that result.
   - The app's own views stay responsive while a query runs.
2. **Run the integration tests** when Docker is up: `uv run pytest tests/integration/routes/v1/test_chat_route.py` in `backend/`.
3. **Build the backend image** once, to check the `docs` build context.
4. **Edit the three greeting texts** in `frontend/src/features/project/components/ai-chat-view.tsx`. They are drafts.
5. **Push and open the PRs.** Nothing is on GitHub yet. Step 1 (`a6b2d42`) can go first, with step 2 stacked on it.
6. **The two open points at the end of this plan** stay as they are, as you said.

### To decide whether step 2 ships

7. **Test a hosted model on the same questions.** If it gets nearly all 14 right, step 2 is worth showing. If not, the query catalogue from the earlier discussion is the fallback: the same table UI, with predefined queries the model picks from. The questions:
   - What is the installed capacity per carrier?
   - How many generators are there per carrier?
   - Which 5 generators have the highest capital cost?
   - What is the total solar capacity?
   - What is the average marginal cost by carrier?
   - How many buses are there per country?
   - Which lines are the longest?
   - What is the average availability of onshore wind?
   - What is the total capacity of offshore wind?
   - What is the average lifetime of generators by carrier?
   - Which generators have the largest maximum capacity?
   - What is the average efficiency of CCGT generators?
   - How many buses are there?
   - How many lines connect each pair of buses?
   - Docs: How do I start a run? What is a playbook? What does the Inspect stage show?
8. **Add a `CHAT_REASONING_EFFORT` setting** if the hosted model is a thinking model. The backend does not send one today.
9. **Extend the prompt for run results**: an example with the snapshot weights, and one for a per-connection attribute such as `p`.
10. **Charts**, as discussed: a bar chart through `ChartSpec` is about a day on top of the table.

### Before any deployment

The section "Before any deployment" below still holds. Step 2 adds:

- **The record server's shared token.** A model's query can read any project's data on that server, as the app's own reads can. This goes away with the datarecord session (#322).
- **The datarecord session replaces the record server.** Only `frontend/src/features/chat/run-sql.ts` and `record-context.ts` read it.
- **The DPO review**: with step 2, the names in a project's data go to the model provider. Values do not.

## Context

An AI chat is part of the 2026 deliverables, and no option, provider, or owner is chosen yet (issues #260 and #110). The frontend has a mock "Ask Rai" drawer with canned replies, and the backend has no LLM code.

This plan builds a prototype that is fast to ship and adds little to the threat boundary:

- **Step 1:** a free-text chat that answers from Manta's documentation, with streamed replies.
- **Step 2:** the model writes SQL about the open project's results, the user's browser runs it, and the chat shows a result table.

Decisions already made:

- The model runs on local Ollama for now, behind an OpenAI-compatible chat-completions API, so a hosted EU provider is a config change later.
- It starts as a local demo. If step 1 merges this week it can join the pentest; otherwise it targets the beta.
- Replies stream over SSE.

## Design rules

- The model has no server-side tools and no data access. The backend's only new privilege is calling the model endpoint, so a prompt injection can change only the text shown to the user who typed it.
- The chat is off unless configured (`CHAT_ENABLED=false` by default).
- History is stateless: the browser sends the recent messages, and the server accepts only the `user` and `assistant` roles and prepends its own `system` message. No chat messages are stored, which also removes the "chat messages in the app database" row from the DPO review.
- No new backend dependency: the client is `httpx2`, which the backend already uses.
- Replies render as plain text (`whitespace-pre-wrap`) for now. The system prompt asks for answers without Markdown. No new frontend dependency.
- Streaming stays inside the sync rule in AGENTS.md: a plain `def` route that yields, with `response_class=EventSourceResponse` from `fastapi.sse` (present in the installed FastAPI 0.141.1). Each generation holds one worker thread, which the concurrency cap bounds.

## Model and limits

### Model: `llama3.2:3b`

| Model | Download | Notes |
|---|---|---|
| `llama3.2:3b` (chosen) | 2.0 GB | Already installed on this machine. No thinking mode, so no extra setting. |
| `qwen3.5:2b` | 2.7–3.1 GB | Thinking model: needs `reasoning_effort: "none"`. A candidate for step 2. |
| `qwen3.5:4b`, `gemma3:4b` | 3.3–4.0 GB | Too large next to the stack on 8 GB. |

- This machine is an M2 with 8 GB, and Docker's VM takes 3.8 GB of it. That leaves about 4 GB for macOS and the model, so 2 GB is the practical ceiling. Expect some swapping while the full stack runs.
- Ollama's default context is 4k on this hardware, and its OpenAI-compatible route cannot set the context per request. A prompt that does not fit is cut off without an error. So the setup creates a named model with a fixed context:
  - `Modelfile`: `FROM llama3.2:3b` and `PARAMETER num_ctx 8192`
  - `ollama create manta-chat -f Modelfile`, then `CHAT_MODEL=manta-chat`
- Speed is unmeasured. The first question has to process the whole docs prompt, which I expect to take tens of seconds on this machine; later questions should reuse it. Verification step 3 measures both.

### Context budget (8,192 tokens)

Counted at 3.5 characters per token, the pessimistic end for English prose:

| Part | Cap | Tokens |
|---|---|---|
| Docs in the system message | 20,000 characters | about 5,700 |
| Instructions and chat template | | about 250 |
| History sent by the browser | 6,000 characters | about 1,700 |
| Reply | 400 tokens | 400 |
| **Total** | | **about 8,050** |

### Limits

| Limit | Enforced in | Client sees |
|---|---|---|
| Signed in | `Security(authenticated_user)` | 401, existing refresh |
| Chat enabled | `require_chat_enabled` dependency | 404 |
| Roles `user` and `assistant` only, last message from `user` | `ChatRequest` validation | 422 |
| At most 12 messages, 2,000 characters each, 6,000 in total | `ChatService`, from config | 422 |
| Concurrent generations | `chat_slot` dependency (a process-wide semaphore) | 429 with `Retry-After` |
| Reply length | `max_tokens` sent upstream | `done` with `finish_reason: "length"` |
| Time | `httpx2` read timeout plus a deadline | `error` with `code: "timeout"` |

- The message limits are config values, so a hosted model with a larger context raises them without a code change.
- The browser reads the limits from the status route and drops the oldest turns to fit.
- Per-user rate limits and token budgets are left to the planned rate-limit work (#210).

## Step 1: docs chat

### API

- `GET /v1/chat/status` returns `{enabled, max_messages, max_message_chars, max_history_chars}`. It answers when chat is disabled too.
- `POST /v1/chat/messages` takes `{"messages": [{"role": "user", "content": "…"}]}` and returns SSE events:
  - `delta` with `{"text"}`
  - `done` with `{"finish_reason": "stop" | "length"}`
  - `error` with `{"code": "model_unavailable" | "timeout", "message"}`
- Failures before the stream starts are ordinary JSON errors. The client treats a stream that ends without `done` or `error` as interrupted.

### Docs in the prompt

- An ordered page list, by default the four `user-guide` pages (17,114 characters today). `docs/index.md` is left out of the default: with it the total is 19,846, which is within 154 characters of the cap.
- The system message is built once at startup and contains nothing per request, so the model server can reuse it between requests, and provider-side prompt caching works later. Startup fails if a page is missing or the text exceeds the cap.
- The docs reach the image through a fourth named build context, as `backend/Dockerfile` already does for `playbook` and `runner`.

### Config (`backend/src/manta/config/chat_config.py`)

| Variable | Default |
|---|---|
| `CHAT_ENABLED` | `false` |
| `CHAT_BASE_URL`, `CHAT_MODEL` | required when enabled |
| `CHAT_API_KEY` | unset |
| `CHAT_MAX_OUTPUT_TOKENS` | `400` |
| `CHAT_MAX_MESSAGES` | `12` |
| `CHAT_MAX_MESSAGE_CHARS` | `2000` |
| `CHAT_MAX_HISTORY_CHARS` | `6000` |
| `CHAT_MAX_CONCURRENT` | `2` |
| `CHAT_TIMEOUT_SECONDS` | `120` |
| `CHAT_DOCS_DIR` | the repo's `docs/` |
| `CHAT_DOCS_PAGES` | the four `user-guide` pages |
| `CHAT_DOCS_MAX_CHARS` | `20000` |

Follow the existing pattern in `config/s3_config.py`: one function per variable, with `@lru_cache` for the `httpx2.Client` and the semaphore.

### Files to add

- `backend/src/manta/config/chat_config.py`
- `backend/src/manta/routes/v1/requests/chat_request.py`: `ChatMessage` and `ChatRequest`.
- `backend/src/manta/services/results/chat_result.py`: `GetChatStatusResult` and `ChatEventResult`.
- `backend/src/manta/services/chat_service.py`: `system_prompt()`, `require_chat_enabled()`, `chat_slot()`, `ChatService.status()`, and `ChatService.stream_reply(messages)`, which checks the message limits, catches upstream failures, and emits an `error` event.
- `backend/src/manta/routes/v1/chat_route.py`: the two routes. The streaming route releases the database session before the first yield.
- `frontend/src/features/chat/sse.ts`: `readSseEvents(body)`.
- `frontend/src/features/chat/api.ts`: `useChatStatus()` and `streamChatReply(messages, signal)`.

### Files to change

- `backend/src/manta/routes/v1/__init__.py`: include the router.
- `backend/src/manta/main.py`: build the prompt at startup when chat is enabled.
- `backend/Dockerfile`, `docker/compose-dev-backend.yaml`, and `.github/workflows/docker-build.yml`: add the `docs` build context and `CHAT_DOCS_DIR`.
- `backend/.env`: add `CHAT_ENABLED=false` and commented examples only, because the deploy reads this file.
- `frontend/src/api/manta.ts`: split `requestJson` so an authorised fetch returns the `Response`, and add `postStream`. The 401 refresh-and-retry then runs before any body is read.
- `frontend/src/features/project/components/ai-chat-view.tsx`:
  - Replace the canned replies with the stream, and add a stop button and an error state.
  - Enabled greeting (draft, keeping the current introduction): "I can answer questions from the Manta documentation. Questions about your project's results are coming soon."
  - Disabled greeting (draft): "Chat isn't enabled in this deployment. Coming soon: answers from the Manta documentation, and questions about your results, answered with tables." The input is disabled. The same state shows if the status request fails.
- `frontend/src/features/project/components/header.tsx`: no change. The "Ask Rai" button always shows.

### Tests

- `backend/tests/unit/services/test_chat_service.py`, with `httpx2.MockTransport` as in `test_example_data_service.py`: delta parsing; upstream 500, connect error, and timeout each become `error`; each message limit; the system message comes first and is identical across calls; the `Authorization` header is sent only when a key is set; the default page selection fits the cap.
- `backend/tests/unit/routes/v1/requests/test_chat_request.py`: rejection of the `system` role, and of a last message that is not from `user`.
- `backend/tests/integration/routes/v1/test_chat_route.py`: 401, a streamed reply, 422, and 429 while a slow stream holds the slot, against a small fake completions server started in `conftest.py`.
- `frontend/src/features/chat/__tests__/sse.test.ts` and `api.test.ts`.

### Docs in the same PR

- Add an architecture design doc of this step at `docs/design/chat.md`, with a nav entry in `mkdocs.yml`. The docs build is strict, so a page outside the nav fails it.
- `docs/reference/backend/openapi.json`: regenerate, since CI checks the export.
- `backend/README.md`: how to run the chat locally with Ollama, including the `Modelfile` above.

Use the `docs-writing` and `prose-writing` skills for these.

## Step 2: SQL with a result table (after step 1 merges)

- **Format:** the model returns one fenced `sql` block, which works across providers and small local models. No tool calling.
- **Schema:** a static reference page on the record views, written from `docker/quack-server/app/manta_views.py`, joins the system prompt. `ChatRequest` gains an optional `record` field (catalogue name, attribute names with dimensions, zone levels), validated and capped. A `CHAT_SQL_ENABLED` flag gates it.
- **Execution:** a new `frontend/src/features/chat/run-sql.ts` accepts one statement, rejects `;` and `$$`, wraps it as `SELECT * FROM (…) LIMIT 201`, and runs it with a timeout. It uses `serverQuery` only, because `query()` runs in the browser's own DuckDB, where model SQL could attach databases or read URLs.
- **Retry:** rows are not sent to the model. A DuckDB error, capped at 500 characters, goes back once.
- **Table:** a new small `result-table.tsx` in the chat feature, with the SQL in a collapsible block. `series-table.tsx` only takes numeric series and `data-table.tsx` is tied to the level store.
- **Dependency:** all of this reads through the Quack record server, which the datarecord session (#322) replaces, so execution stays behind the one `run-sql.ts` function.
- **Model:** the schema and record context do not fit beside the docs in 8,192 tokens, and I expect a 3B model to write unreliable SQL. Step 2 starts by testing `qwen3.5:2b` and a hosted model on a short list of questions, and sizes its caps from the result.

## Before any deployment (not in the prototype PRs)

- Raise the backend-service timeout on the GCP load balancer (`scripts/deploy/gcp-register-lb.sh` sets none).
- Check that Caddy flushes `text/event-stream` without a directive, and add a request body size limit.
- Per-user rate limits and token budgets (#210).
- Choose the model host: a hosted EU provider, or an Ollama server. Size the docs and history limits to its context. Keep any API key out of the committed `backend/.env`.
- Update the DPO review (messages are sent to the model but not stored) and the trust boundaries (#71).

## Workflow

- Branch `sid/chat-docs-prototype` from `main`.
- Before each commit: `uvx pre-commit run --all-files`, the backend unit tests, and the integration tests when Docker is available. Commit once they pass.

## Verification

1. Restart Ollama so the server matches the client (the server reports 0.35.1 and the client 0.40.17). Create `manta-chat` from the `Modelfile`, load it, and check that `ollama ps` shows a context of 8192.
2. Set `CHAT_ENABLED=true`, `CHAT_BASE_URL=http://localhost:11434/v1`, `CHAT_MODEL=manta-chat`, and `CHAT_MAX_CONCURRENT=1`, then start the stack.
3. Open a project, click "Ask Rai", and ask a question the user guide answers. The reply streams, and stop cancels it. Note the time to the first token for the first question and for a follow-up.
4. Ask something outside the docs and try a prompt injection. Only the text in that user's own drawer changes.
5. Send two requests at once with `curl`. The second gets a 429.
6. Stop Ollama and send a message. The drawer shows the error state.
7. Set `CHAT_ENABLED=false` and restart the backend. The "Ask Rai" panel shows chat isn't available and the route returns 404.
8. Run the backend unit and integration tests, and `npm test` in `frontend/`.

## Open points

1. **`docs/design/` does not exist on `main`.** AGENTS.md names it, but PR 303 moved its design pages under `docs/explanation/`. The plan creates `docs/design/chat.md` as you wrote. Change the path here if you want `docs/explanation/chat.md` instead.
2. **`docs/explanation/planned-changes.md` line 126** lists a language-model provider among the systems Manta "does not talk to today". You removed that update from the plan. Once chat merges the sentence is out of date, so I suggest a one-line edit there. The plan leaves it out unless you add it back.
