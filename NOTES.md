# AgentCore implementation notes

## Agent loop

Each Celery task loads the owned session and run, marks the run as running, builds a prompt from the session instructions, the most recent Redis messages, and up to three semantically similar memories for the same user. It calls the configured chat model with schemas generated from the registered Python tool signatures. Tool calls and results are appended to the conversation and persisted as separate run steps. The loop stops on a plain assistant response or after ten model calls.

Step records are committed before publishing their Redis Pub/Sub event. The run is marked complete before its final event is sent. Failures are recorded as an error step and mark the run failed.

## Memory strategy

Redis stores up to 20 individual user/assistant messages per session, with the last 10 supplied as context. This bounds prompt growth and keeps sessions separate. Long-term facts are embedded with `text-embedding-3-small`, scoped by user, and ranked by pgvector cosine distance. The query currently sorts that user's memory rows directly; add a vector index such as HNSW or IVFFlat and benchmark it as memory volume grows.

## Tool behavior

Tool definitions are derived from function signatures and annotations. The calculator evaluates a small allowlist of arithmetic AST nodes rather than evaluating arbitrary Python. Mock search returns sample snippets. Chat can use OpenAI or Groq by setting `LLM_PROVIDER`; Groq uses its OpenAI-compatible chat endpoint. Semantic memory embeddings still use OpenAI's `text-embedding-3-small`, so long-term memory needs `OPENAI_API_KEY` even when Groq handles chat. Without an embedding key, the agent runs with short-term Redis memory and reports persistent-memory tools as unavailable.

## Deliberate assessment tradeoffs

- The document says refresh tokens are unnecessary but its endpoint table mentions one; this implementation follows the explicit feature requirement and returns an access token only.
- Authentication/login accepts JSON credentials for a compact API. Passwords are hashed with bcrypt and access tokens expire after 30 minutes.
- Cancellation requests Celery task revocation and marks the database run cancelled. Worker termination is best-effort; hard process termination and cancellation races need production-specific handling.
- Redis history is a bounded message window, not a complete transcript store. PostgreSQL run steps are the durable trace.
- A production deployment should run Alembic migrations as a release step. The API currently also creates missing tables on startup to simplify local setup.
- Retries, concurrent-run rate limiting, OpenAPI response enrichment, structured logging, and automated tests are follow-up improvements given the 90-minute limit.

## Start locally

Install Python 3.12, PostgreSQL with pgvector, and Redis, then start those services locally. Copy `.env.example` to `.env`, add the API key for the selected chat provider, and install Python dependencies with `pip install -r requirements.txt`. Start the Celery worker with `celery -A app.celery_app.celery_app worker --loglevel=info` and the API with `uvicorn app.main:app --reload` in separate terminals. The API docs are at `http://localhost:8000/docs`.
