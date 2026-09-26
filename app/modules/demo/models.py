from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

class Note(SQLModel, table=True):
    __tablename__ = "demo_note"  # Đặt prefix để tránh trùng bảng

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=200)
    content: str = Field(default="")
    # Sửa ở đây: dùng datetime.now(timezone.utc) thay vì datetime.utcnow
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))