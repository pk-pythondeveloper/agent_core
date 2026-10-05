import json
from openai import AsyncOpenAI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent import AgentRun, AgentSession, LongTermMemory, RunStatus, RunStep
from app.redis_client import redis
from app.agent.tools import TOOL_DEFINITIONS, dispatch_tool
from app.database import AsyncSessionLocal
from app.llm import chat_client, chat_model, embedding_client


async def _record(db: AsyncSession, run: AgentRun, step_type: str, payload: dict):
    step = RunStep(run_id=run.id, step_type=step_type, payload=payload)
    db.add(step)
    await db.commit()
    event = json.dumps({"step_type": step_type, "payload": payload}, default=str)
    await redis.publish(f"run:{run.id}", event)


async def execute_agent_run(run_id: str):
    if not chat_client:
        raise RuntimeError("Configure the selected LLM provider API key in .env")
    async with AsyncSessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        if not run or run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            return
        run.status = RunStatus.RUNNING
        await db.commit()
        session = await db.get(AgentSession, run.session_id)
        if not session:
            raise RuntimeError("Agent session no longer exists")
        enabled = [name for name in session.tools_enabled if name in TOOL_DEFINITIONS]
        # Load a bounded recent context window from Redis.
        raw_history = await redis.lrange(f"session:{session.id}:history", -10, -1)
        history = [json.loads(item) for item in raw_history]
        # Retrieve this user's most relevant saved facts when embeddings are available.
        memories = []
        if embedding_client:
            embedding = (await embedding_client.embeddings.create(model="text-embedding-3-small", input=run.user_message)).data[0].embedding
            memories = (await db.execute(select(LongTermMemory).where(LongTermMemory.user_id == session.user_id)
                .order_by(LongTermMemory.embedding.cosine_distance(embedding)).limit(3))).scalars().all()
        system = session.system_prompt or "You are a helpful assistant. Use tools when useful and respond clearly."
        if memories:
            system += "\nRelevant long-term memories:\n" + "\n".join(f"- {m.content}" for m in memories)
        elif not embedding_client:
            system += "\nLong-term memory embeddings are not configured, so do not claim to save or retrieve persistent facts."
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": run.user_message}]
        final_answer = "Max iterations reached"
        for iteration in range(10):
            tool_schemas = [TOOL_DEFINITIONS[name] for name in enabled]
            response = await chat_client.chat.completions.create(model=chat_model, messages=messages,
                tools=tool_schemas or None, tool_choice="auto" if tool_schemas else None)
            choice = response.choices[0].message
            run.tokens_used += response.usage.total_tokens if response.usage else 0
            await _record(db, run, "llm_call", {"iteration": iteration + 1, "content": choice.content, "tool_calls": [tc.model_dump() for tc in (choice.tool_calls or [])]})
            if not choice.tool_calls:
                final_answer = choice.content or ""
                break
            messages.append(choice.model_dump(exclude_none=True))
            for call in choice.tool_calls:
                name = call.function.name
                args = call.function.arguments
                await _record(db, run, "tool_call", {"tool": name, "arguments": args})
                if name not in enabled:
                    result = f"Tool error: '{name}' is not enabled for this session."
                else:
                    result = await dispatch_tool(name, args, db=db, user_id=session.user_id, run_id=run.id)
                await _record(db, run, "tool_result", {"tool": name, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        run.final_answer = final_answer
        run.status = RunStatus.COMPLETED
        await db.commit()
        await _record(db, run, "final_answer", {"answer": final_answer})
        await redis.rpush(f"session:{session.id}:history", json.dumps({"role": "user", "content": run.user_message}))
        await redis.rpush(f"session:{session.id}:history", json.dumps({"role": "assistant", "content": final_answer}))
        await redis.ltrim(f"session:{session.id}:history", -20, -1)
        await redis.publish(f"run:{run.id}", json.dumps({"step_type": "done", "status": "completed"}))


async def execute_agent_run_safe(run_id: str):
    async with AsyncSessionLocal() as db:
        # Atomic claim prevents two workers from executing a duplicate delivery.
        claimed = await db.execute(update(AgentRun).where(
            AgentRun.id == run_id, AgentRun.status == RunStatus.QUEUED
        ).values(status=RunStatus.RUNNING))
        if claimed.rowcount != 1:
            return
        await db.commit()
    try:
        await execute_agent_run(run_id)
    except Exception as exc:
        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            if run and run.status not in (RunStatus.COMPLETED, RunStatus.CANCELLED):
                run.status = RunStatus.FAILED
                await db.commit()
                await _record(db, run, "error", {"error": f"{type(exc).__name__}: {exc}"})
                await redis.publish(f"run:{run.id}", json.dumps({"step_type": "done", "status": "failed"}))
        raise
