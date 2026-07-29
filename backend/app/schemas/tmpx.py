import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TmpxItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value: int = 0


class TmpxItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    value: int
    created_at: datetime
