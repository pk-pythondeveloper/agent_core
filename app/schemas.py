from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.agent import RunStatus


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionCreate(BaseModel):
    name: str
    system_prompt: str = ""
    tools_enabled: list[str] = Field(default_factory=list)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    system_prompt: str
    tools_enabled: list[str]
    created_at: datetime


class RunCreate(BaseModel):
    message: str = Field(min_length=1)


class RunOut(BaseModel):
    run_id: str
    status: RunStatus


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    step_type: str
    payload: dict
    occurred_at: datetime


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    content: str
    created_at: datetime
