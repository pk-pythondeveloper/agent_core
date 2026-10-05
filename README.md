# AgentCore

FastAPI backend assessment: authenticated agent sessions, queued runs, tool calling, Redis streaming and memory, and pgvector long-term memory.

## Run locally

Install Python 3.12, PostgreSQL with the pgvector extension, and Redis. Create a PostgreSQL database named `agentcore` and a database user matching the URL in `.env.example`, with pgvector available in that database. Start PostgreSQL and Redis, then:

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add the API key for your selected model provider.
4. In one terminal, start the worker with `celery -A app.celery_app.celery_app worker --loglevel=info`.
5. In another terminal, start the API with `uvicorn app.main:app --reload`.
6. Open `http://localhost:8000/docs`.

The API initializes the schema at startup. For migration-based setup, run `alembic upgrade head` after PostgreSQL is available.

See [NOTES.md](NOTES.md) for the loop design and known tradeoffs.

For the complete walkthrough from local setup through submitting a task and troubleshooting, see [USER_GUIDE.md](USER_GUIDE.md).
