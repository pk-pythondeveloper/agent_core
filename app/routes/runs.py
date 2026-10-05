import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.models.agent import AgentRun, AgentSession, RunStatus, RunStep
from app.models.user import User
from app.schemas import RunCreate, RunOut, StepOut
from app.redis_client import redis
from app.tasks import execute_agent_run_task
from app.database import AsyncSessionLocal

router = APIRouter(tags=["runs"])


async def owned_run(run_id, user, db):
    run = await db.scalar(select(AgentRun).join(AgentSession).where(AgentRun.id == run_id, AgentSession.user_id == user.id))
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/sessions/{session_id}/run", response_model=RunOut, status_code=202)
async def start_run(session_id: str, body: RunCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    session = await db.scalar(select(AgentSession).where(AgentSession.id == session_id, AgentSession.user_id == user.id))
    if not session:
        raise HTTPException(404, "Session not found")
    run = AgentRun(session_id=session.id, user_message=body.message, status=RunStatus.QUEUED)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    execute_agent_run_task.apply_async(args=[run.id], task_id=run.id)
    return RunOut(run_id=run.id, status=run.status)


@router.get("/runs/{run_id}/status")
async def run_status(run_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await owned_run(run_id, user, db)
    count = await db.scalar(select(func.count(RunStep.id)).where(RunStep.run_id == run.id))
    return {"run_id": run.id, "status": run.status, "tokens_used": run.tokens_used, "step_count": count, "created_at": run.created_at, "final_answer": run.final_answer}


@router.get("/runs/{run_id}/steps", response_model=list[StepOut])
async def run_steps(run_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await owned_run(run_id, user, db)
    return (await db.scalars(select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.occurred_at, RunStep.id))).all()


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await owned_run(run_id, user, db)
    initial_status = run.status.value
    async def events():
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"run:{run_id}")
        try:
            if initial_status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'step_type':'done','status':initial_status})}\n\n"
                return
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message and message.get("data"):
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    try:
                        if json.loads(data).get("step_type") == "done":
                            break
                    except (ValueError, AttributeError):
                        pass
                else:
                    yield ": keep-alive\n\n"
                    # Pub/Sub is transient. Poll durable state too, so a subscriber that
                    # connects after the final publish still receives a terminal event.
                    async with AsyncSessionLocal() as check_db:
                        latest = await check_db.get(AgentRun, run_id)
                        status = latest.status.value if latest else "failed"
                    if status in ("completed", "failed", "cancelled"):
                        yield f"data: {json.dumps({'step_type':'done','status':status})}\n\n"
                        break
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(f"run:{run_id}")
            await pubsub.aclose()
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})


@router.delete("/runs/{run_id}", status_code=204)
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await owned_run(run_id, user, db)
    if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
        return
    execute_agent_run_task.AsyncResult(run.id).revoke(terminate=True, signal="SIGUSR1")
    run.status = RunStatus.CANCELLED
    await db.commit()
    await redis.publish(f"run:{run.id}", json.dumps({"step_type":"done","status":"cancelled"}))
