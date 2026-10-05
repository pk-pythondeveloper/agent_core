from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.agent import LongTermMemory
from app.models.user import User
from app.schemas import MemoryOut
from app.llm import embedding_client

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryOut])
async def list_memory(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return (await db.scalars(select(LongTermMemory).where(LongTermMemory.user_id == user.id).order_by(LongTermMemory.created_at.desc()))).all()


@router.get("/search", response_model=list[MemoryOut])
async def search_memory(q: str = Query(min_length=1), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not embedding_client:
        raise HTTPException(503, "OPENAI_API_KEY is required for semantic memory embeddings")
    vector = (await embedding_client.embeddings.create(model="text-embedding-3-small", input=q)).data[0].embedding
    return (await db.scalars(select(LongTermMemory).where(LongTermMemory.user_id == user.id)
        .order_by(LongTermMemory.embedding.cosine_distance(vector)).limit(5))).all()


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    item = await db.scalar(select(LongTermMemory).where(LongTermMemory.id == memory_id, LongTermMemory.user_id == user.id))
    if not item:
        raise HTTPException(404, "Memory not found")
    await db.delete(item)
    await db.commit()
