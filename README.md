# Datastraw CX Assistant

AI-assisted customer-support workspace for more than one brand. An agent opens a conversation, generates a reply from that brand’s policies, reviews the retrieved knowledge, edits the draft, approves it, and sends it into the thread.

AquaPure and GlowNest are the sample brands. Each brand has its own customers, orders, conversations, and policies. A reply for one brand does not use the other brand’s knowledge.

## Features

- Inbox, conversation thread, customer message, and manual agent reply.
- Brand knowledge base with return, refund, shipping, and cancellation policies.
- PostgreSQL full-text retrieval limited to the conversation’s brand.
- Synchronous AI draft through OpenRouter, with the API key kept on the server.
- Server-side guardrails that block unsupported refund promises and invented policy.
- Edit, approve, and send. Approve does not send. Send posts one agent message.
- Manual replies send the agent’s own text and do not create an AI generation record.
- Idempotency for manual replies and for a repeated AI send.
- Generation history for a conversation: retrieved policy titles, model, timing, token counts, evidence, and warnings. Provider secrets are not stored.
- Empty, loading, and error states in the UI.

## Architecture

The React app talks to a FastAPI process. In development, Vite proxies `/api` to the API so the browser stays on one origin. The API uses async SQLAlchemy and PostgreSQL.

```
Browser
  → Vite (dev) or static host (production)
  → FastAPI
       conversations, knowledge, retrieval, generation, approval
       guardrails
       OpenRouter (only when a key is configured and knowledge was retrieved)
  → PostgreSQL
```

Brand comes from the conversation or the knowledge row on the server. Retrieval, generation, and approval do not trust a brand id supplied by the client. Generation is a single request and response. There is no queue, cache, or vector database.

## Technology choices

- **React and Vite.** The UI is one workspace: inbox, thread, and reply panel. No router and no component library.
- **FastAPI and async SQLAlchemy.** Request handlers stay async. Services commit their own work.
- **PostgreSQL.** Brand isolation is enforced with foreign keys and brand-scoped queries. Policy search uses a generated `tsvector` and a GIN index.
- **OpenRouter.** One chat-completions call returns a JSON draft. The key is an environment variable on the API process.
- **Alembic.** Schema changes are versioned migrations.
- **psycopg.** The same driver serves the async API and the sync Alembic and seed commands.

Redis, Celery, Qdrant, Kafka, and a separate retrieval service are intentionally absent.

## Folder structure

```
backend/
  alembic/                migrations
  app/
    api/                  HTTP routes
    core/                 settings, database, errors, Windows event loop
    models/               SQLAlchemy models
    schemas/              request and response models
    services/             conversations, knowledge, retrieval, generation,
                          guardrails, approval, OpenRouter client
    seed.py               sample AquaPure and GlowNest data
  tests/                  script-style checks
  requirements.txt
  alembic.ini
  .env.example
frontend/
  src/
    components/           inbox, thread, reply panel, knowledge UI
    pages/KnowledgePage.tsx
    api.ts                fetch helpers for /api
    hooks/useInbox.ts
  vite.config.ts          dev server and /api proxy
```

## Database schema

PostgreSQL 15 or newer. Primary keys are UUIDs. `created_at` and `updated_at` are timestamps. `set_updated_at()` updates `updated_at` on brands, customers, knowledge, orders, conversations, and messages.

| Table | Purpose | Important columns |
| --- | --- | --- |
| `brands` | One support brand | `name`, unique `slug` |
| `customers` | Customer of one brand | `brand_id`, `full_name`, `email` unique per brand |
| `orders` | Order owned by that customer and brand | `order_number`, `product_name`, `status`, `total_cents`, `currency`, `placed_at`, nullable `delivered_at` |
| `conversations` | Thread for one order | `subject`, `status` (`open` or `resolved`) |
| `messages` | Customer or agent text | `author_type` (`CUSTOMER` or `AGENT`), `body`, nullable `idempotency_key` |
| `knowledge_base_entries` | Active policies | `category` (`RETURN`, `REFUND`, `SHIPPING`, `CANCELLATION`), `title`, `content`, `active`, generated `search_vector` |
| `ai_generation_logs` | One draft and its later approval | `suggested_reply` (original, not overwritten), `edited_reply`, `final_reply`, `evidence_status`, `warning`, `error_detail`, `retrieved_knowledge_ids`, `retrieved_context`, `model_name`, `latency_ms`, token counts, `status`, `sent_message_id` |

Order status is `pending`, `paid`, `shipped`, `delivered`, or `cancelled`.

Generation status is `AI_GENERATED`, `EDITED`, `APPROVED`, or `SENT`. A row becomes `SENT` only through the send endpoint, which stores `final_reply` and the agent message id.

Evidence status is `SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_INFORMATION`, or `HUMAN_REVIEW_REQUIRED`.

Customers, orders, conversations, messages, and generation logs are tied to the parent brand with composite foreign keys, so a row cannot point at another brand’s customer, order, or message.

## Environment variables

Copy `backend/.env.example` to `backend/.env`. The process reads that file. Every variable below is required to be present or has a default in code. `DATABASE_URL` has no default and must be set.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | Yes | none | `postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE` |
| `CORS_ORIGIN` | No | `http://localhost:5173` | Origin allowed by CORS |
| `APP_NAME` | No | `Datastraw CX Assistant` | FastAPI application title |
| `OPENROUTER_API_KEY` | No | empty | Server-only model key. Empty skips the provider call |
| `OPENROUTER_MODEL` | No | `openai/gpt-4o-mini` | Model id |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | Provider root URL |
| `OPENROUTER_TIMEOUT_SECONDS` | No | `20` | Provider timeout in seconds |

Do not commit `backend/.env`. Do not put a real key in `.env.example` or in the React app.

## Local setup

Install Python 3.12 or newer, Node.js 20 or newer, and PostgreSQL 15 or newer.

Create a database and a login that can create tables in it. The names below match the placeholders in `.env.example`. Use a different port if `5432` is already another cluster.

```sql
CREATE USER cx_user WITH PASSWORD 'choose-a-password';
CREATE DATABASE cx_assistant OWNER cx_user;
```

From the repository root:

```bash
cd backend
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

macOS or Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set `DATABASE_URL` to the database you created. Then migrate and load the sample brands:

```bash
python -m alembic upgrade head
python -m app.seed
```

Run these commands from `backend` so Python can import `app`.

## Database migration instructions

Migrations live in `backend/alembic`. Alembic reads `DATABASE_URL` from `backend/.env`.

From `backend`, with the virtual environment active:

```bash
python -m alembic upgrade head
```

Confirm the current revision:

```bash
python -m alembic current
```

The head revision is `b7e2c4a91d18`.

Apply migrations before starting the API and before seeding. To move an existing database forward, run `python -m alembic upgrade head` again after pulling new revisions.

## Seed instructions

From `backend`:

```bash
python -m app.seed
```

The command inserts AquaPure and GlowNest, each with customers, orders, conversations, messages, and four policies. Brand ids are stable UUID5 values, so the same slugs refer to the same brands on every seed.

Running the seed again deletes those two brands and their customers, orders, conversations, messages, policies, and generation logs, then inserts the sample set. Messages and drafts created in the UI for those brands are removed. Run it when you want a clean sample workspace.

## Running backend

From `backend`, with the virtual environment active:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --loop app.core.event_loop:loop_factory
```

Port **8001** is required. The Vite proxy and the HTTP tests call `http://127.0.0.1:8001`. On Windows, uvicorn’s default event loop cannot drive psycopg. The `--loop` flag selects a compatible loop and is safe on other operating systems too.

Check the process:

```bash
curl http://127.0.0.1:8001/health
```

A ready API returns:

```json
{"status":"ok","database":"ok"}
```

Interactive API docs are at `http://127.0.0.1:8001/docs`.

## Running frontend

From `frontend`:

```bash
npm install
npm run dev
```

Open the URL Vite prints. The configured port is `5173`. If that port is taken, Vite uses the next free port. API calls go to `/api` on that same origin, and Vite forwards them to `http://127.0.0.1:8001`.

The reply panel is the main path: customer message, Generate Reply, retrieved knowledge, AI draft, Edit, Approve, Send, then the conversation history.

`npm run build` typechecks and writes a static build to `frontend/dist`.

## Running tests

Tests are Python scripts in `backend/tests`. They are not a pytest suite. Run them from `backend` with the virtual environment active, after migrations and seed.

These talk to the API on port 8001, so the backend must already be running:

```bash
python tests/test_knowledge_api.py
python tests/test_conversations_api.py
python tests/test_retrieval.py
python tests/test_manual_reply.py
python tests/test_e2e_flow.py
```

These use the database or in-process services and do not need the HTTP server:

```bash
python tests/test_generation.py
python tests/test_guardrails.py
python tests/test_generate_reply.py
python tests/test_approval.py
python tests/test_generation_log.py
```

A script prints a short “passed” line and exits 0. A failed check exits with a message.

`test_conversations_api.py` expects exactly two conversations for each seeded brand. Extra threads left in the database fail that count. `test_e2e_flow.py` and `test_manual_reply.py` write messages and temporarily change a policy, then restore or delete what they created. Use a database you are willing to have those tests touch.

`test_generation.py` logs `Reply provider HTTP 401` on purpose while it checks a provider error. That line is not a failed test.

## AI configuration

Set `OPENROUTER_API_KEY` in `backend/.env` and restart the API. The server sends it only as the `Authorization: Bearer` header on the request to `{OPENROUTER_BASE_URL}/chat/completions`. The React app never receives the key.

The call asks for one JSON object named `cx_suggested_reply`, with temperature `0.2` and a maximum of 800 completion tokens. `OPENROUTER_MODEL` is the model id. `OPENROUTER_TIMEOUT_SECONDS` is the wait.

When the key is empty, generation does not open a network connection. The draft tells the agent that the provider is not configured and sets evidence to `HUMAN_REVIEW_REQUIRED`. Retrieved knowledge is still returned when the customer message matches policies.

Provider failures (timeout, HTTP error, unreachable host, unreadable body) become a human-review draft. The stored error text is a fixed sentence. If the provider error contains a bearer token, an `sk-` key, or an `api_key` field, that text is replaced before it is saved. Generation history in the UI applies the same redaction again.

Token counts and latency are stored when the provider returns usage. They are not shown on the agent draft. They appear in generation history.

## Deployment instructions

There is no container image in this repository. A small deployment is one PostgreSQL database, one API process, and a static host for `frontend/dist`.

1. Set the environment variables from the table above on the API host. `DATABASE_URL` must point at the production database. Leave the key out of the image and the frontend build.
2. From `backend`, run `python -m alembic upgrade head`.
3. Run `python -m app.seed` only when you want the AquaPure and GlowNest sample. Skip it for a database that already has real brands.
4. Start the API:

   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --loop app.core.event_loop:loop_factory
   ```

5. From `frontend`, run `npm run build`.
6. Serve `frontend/dist` and proxy `/api` to the API process. The UI calls relative `/api` paths, so the browser should see the UI and the API as one origin. If they are different origins, set `CORS_ORIGIN` to the UI origin.
7. Confirm `GET /health` returns `"database": "ok"` before sending traffic.

Put TLS in front of the public host. Do not expose PostgreSQL or `backend/.env`.

## Security and brand isolation

There is no login yet. Anyone who can reach the API can pass a `brand_id`. Isolation is still enforced on the server:

- Knowledge reads, updates, and deletes require `brand_id`. If the row belongs to another brand, the response is **404** and does not reveal that the id exists.
- A `brand_id` in the JSON body that does not match the brand in the path returns **422** and writes nothing.
- Listing conversations, opening a conversation, posting a message, and reading generation history require `brand_id`. A conversation owned by another brand returns **404**.
- Retrieval, generate-reply, edit, approve, and send ignore a client-supplied `brand_id`. They use the brand stored on the conversation or the generation row.
- Retrieval loads only active knowledge for that brand and returns at most five matches.
- The OpenRouter key is read from the environment on the server. It is not a response field. Error text that looks like a credential is replaced before it is stored.

Blank messages are rejected. Manual replies require an `Idempotency-Key` header of 1 to 80 characters with no spaces. Repeating the same key in one conversation returns the original message. Sending an already-sent generation returns the same agent message.

## AI guardrails

Guardrails run on the server after retrieval and again on the model text. The model’s own evidence label is not trusted. The stored status is the stricter of the server assessment and the model label.

The server will not:

- Promise a refund the retrieved refund policy does not allow.
- Treat “I received this N days ago” as the order’s delivery date. `orders.delivered_at` is the recorded date. A null date is “not recorded.”
- Invent a day count, a dollar amount, an exception, or another brand’s policy.
- Claim a refund, cancellation, shipment, delivery, or prepaid label already happened unless the order record supports that statement. Order status alone does not mean a refund was issued.
- Answer from a policy that was not retrieved. A refund question with no refund policy, or a shipping question with no shipping policy, skips the model and returns `HUMAN_REVIEW_REQUIRED`.

Evidence statuses:

- `SUPPORTED` — the reply matches retrieved policy and recorded order facts.
- `PARTIALLY_SUPPORTED` — the policy is known, but timing or another fact is not recorded. The reply states the policy and does not promise the refund.
- `INSUFFICIENT_INFORMATION` — the order record cannot confirm the question, including “has my refund already been issued?”
- `HUMAN_REVIEW_REQUIRED` — no relevant policy, conflicting policy text, or a draft that cites something that was not retrieved.

`suggested_reply` stays the original text. An edit is stored in `edited_reply`.

## Known limitations

- No authentication or per-agent authorization. Brand checks assume the caller passes the brand they are allowed to see.
- An empty `OPENROUTER_API_KEY` cannot produce a live model completion. The UI still shows retrieved knowledge and a human-review draft.
- Search is English full text, not embeddings. Wording that does not share stems with a policy may retrieve nothing.
- Generation waits on the provider inside the HTTP request. A slow model holds the request until `OPENROUTER_TIMEOUT_SECONDS`.
- The seed replaces AquaPure and GlowNest and their related rows.
- HTTP tests expect the API on port 8001 and, for the conversation count test, exactly the seeded threads.
- The production UI must be served with `/api` proxied to the API, or from an origin listed in `CORS_ORIGIN`. The frontend has no configurable API base URL.
- Conversation status is displayed. The UI does not resolve a conversation.

## Future improvements

- Authenticate agents and take the brand from the signed-in user instead of a query parameter.
- Authorize generation history for the same agent identity.
- Add a test runner and CI around the existing scripts.
- Move generation behind a job only if response time requires it. The current request path is deliberate.
- Add semantic retrieval only if full text misses real customer wording.
- Let an agent mark a conversation resolved.
- Ship a container and a production process manager when the host is chosen.
