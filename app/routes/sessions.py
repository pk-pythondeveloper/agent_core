from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.models.agent import AgentSession, AgentRun
from app.models.user import User
from app.schemas import SessionCreate, SessionOut
from app.agent.tools import TOOL_DEFINITIONS

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return (await db.scalars(select(AgentSession).where(AgentSession.user_id == user.id).order_by(AgentSession.created_at.desc()))).all()


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    unknown = sorted(set(body.tools_enabled) - TOOL_DEFINITIONS.keys())
    if unknown:
        raise HTTPException(422, {"message": "Unknown tool name(s)", "unknown_tools": unknown, "available_tools": sorted(TOOL_DEFINITIONS)})
    item = AgentSession(user_id=user.id, name=body.name, system_prompt=body.system_prompt, tools_enabled=body.tools_enabled)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/{session_id}")
async def session_detail(session_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    item = await db.scalar(select(AgentSession).where(AgentSession.id == session_id, AgentSession.user_id == user.id))
    if not item:
        raise HTTPException(404, "Session not found")
    runs = (await db.scalars(select(AgentRun).where(AgentRun.session_id == session_id).order_by(AgentRun.created_at.desc()).limit(20))).all()
    return {"id": item.id, "name": item.name, "system_prompt": item.system_prompt, "tools_enabled": item.tools_enabled,
            "created_at": item.created_at, "recent_runs": [{"id": r.id, "status": r.status, "final_answer": r.final_answer, "created_at": r.created_at} for r in runs]}


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    item = await db.scalar(select(AgentSession).where(AgentSession.id == session_id, AgentSession.user_id == user.id))
    if not item:
        raise HTTPException(404, "Session not found")
    await db.delete(item)
    await db.commit()
