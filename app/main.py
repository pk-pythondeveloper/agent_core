from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine
from app.models.base import Base
from app import models  # register ORM tables
from app.redis_client import redis
from app.routes import auth, sessions, runs, memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema changes belong in Alembic; this extension call supports first local startup.
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
    yield
    await redis.aclose()
    await engine.dispose()


app = FastAPI(title="AgentCore", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(runs.router)
app.include_router(memory.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
