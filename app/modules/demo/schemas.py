from datetime import datetime
from pydantic import BaseModel

class NoteCreate(BaseModel):
    title: str
    content: str = ""

class NoteRead(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True