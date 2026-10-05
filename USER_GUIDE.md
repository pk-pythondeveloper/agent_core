# AgentCore: simple user guide

Follow these steps to start the app and ask your assistant a question.

## Before you start

Install Python 3.12, PostgreSQL with the pgvector extension, and Redis. Start PostgreSQL and Redis as local services. Create a PostgreSQL database named `agentcore` and a user with access to it. Make sure the pgvector extension is available in that database. The default connection settings are in `.env.example` and use `localhost`, database/user `agentcore`, and password `agentcore`.

You also need a Groq API key for chat answers. Long-term memory embeddings need an OpenAI API key; without it, the app can still run using short-term Redis memory.

## 1. Prepare the project

In PowerShell, open the project folder and run:

```powershell
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set the provider and key in `.env`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=paste_your_own_key_here
GROQ_MODEL=openai/gpt-oss-20b
OPENAI_API_KEY=
```

Replace the placeholder with your Groq key, then save and close Notepad. Keep this key private. Put it only in `.env`; do not put it in `.env.example`, GitHub, a screenshot, or chat. If you want long-term memory, add your OpenAI key to `OPENAI_API_KEY` as well.

## 2. Start the app

Open two PowerShell windows in the project folder. Activate the environment in each window:

```powershell
.\.venv\Scripts\Activate.ps1
```

In the first window, start the background worker:

```powershell
celery -A app.celery_app.celery_app worker --loglevel=info
```

In the second window, start the API:

```powershell
uvicorn app.main:app --reload
```

Keep both windows open. The API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).

## 3. Check the API

Open `GET /health`, click **Try it out**, then **Execute**. You should see `200` and `{"status":"ok"}`.

## 4. Make an account

Open `POST /auth/register`, click **Try it out**, and enter an email and a password with at least 8 characters:

```json
{
  "email": "you@example.com",
  "password": "your-test-password"
}
```

The app will not email you. If it says `Email is already registered`, use the account you made earlier.

## 5. Sign in

Click **Authorize**. Enter your email in **username** and your password in **password**. Leave **client_id** and **client_secret** empty, then click **Authorize**.

## 6. Make an assistant

Open `POST /sessions`, click **Try it out**, and enter:

```json
{
  "name": "My Assistant",
  "system_prompt": "Give clear answers. Use tools when they help.",
  "tools_enabled": ["calculator", "web_search"]
}
```

Click **Execute** and copy the `id` from the response. Tool names must be spelled as shown. `web_search` gives sample results; it does not search the real web.

## 7. Ask a question

Open `POST /sessions/{session_id}/run`. Enter the assistant's ID in `session_id` and use this request body:

```json
{
  "message": "What is 15% of 240?"
}
```

Click **Execute** and copy the `run_id` from the response. The first status is usually `queued`, meaning the worker has received the question.

## 8. See the answer

Use the `run_id` with:

- `GET /runs/{run_id}/status` to check progress and see the answer. Run it again until status says `completed`.
- `GET /runs/{run_id}/steps` to see what the assistant and its tools did.
- `GET /runs/{run_id}/stream` to see updates while the assistant is working.

For the calculator question above, the answer should be 36.

## Stop the app

Press **Ctrl+C** in both PowerShell windows. Your saved accounts and runs stay in PostgreSQL. Recent chat history is stored in Redis.

## If something goes wrong

- **Database connection error:** make sure PostgreSQL is running, the `agentcore` database and user exist, and the values in `.env` match your local setup.
- **Redis connection error or a question stays `queued`:** make sure Redis is running and `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` in `.env` point to it.
- **`401 Unauthorized`:** register first, then sign in with that same email and password.
- **Key missing error:** check `.env` has `LLM_PROVIDER=groq` and your key is on the `GROQ_API_KEY=` line. Restart the worker and API after changing settings.
- **Memory search says unavailable:** long-term memory needs an OpenAI key. Groq is used for chat answers only.

## Sharing this project

Share the project code, `.env.example`, and this guide. Do not share `.env`; it contains your private keys. The other person needs to create their own `.env` and provide their own API keys.
