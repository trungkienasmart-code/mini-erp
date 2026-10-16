# app/modules/tin_tuc/models.py
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class AppNews(SQLModel, table=True):
    __tablename__ = "app_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: str = Field(default="", max_length=100, index=True)
    # ID từ server gốc (để tránh trùng khi sync)

    title: str = Field(max_length=300)
    summary: str = Field(default="", max_length=500)
    content: str = Field(default="")  # TEXT

    news_type: str = Field(default="FEATURE", max_length=20)
    # FEATURE / BUGFIX / PRICE / MODULE / ANNOUNCEMENT / MAINTENANCE

    version: str = Field(default="", max_length=50)
    # Version liên quan (VD: v1.1.0)

    priority: str = Field(default="NORMAL", max_length=20)
    # LOW / NORMAL / HIGH / URGENT

    action_url: str = Field(default="", max_length=300)
    # Link để mua modul, xem chi tiết, ...

    action_label: str = Field(default="", max_length=100)
    # Text của nút (VD: "Xem chi tiết", "Mua ngay")

    is_read: bool = Field(default=False)
    is_pinned: bool = Field(default=False)

    published_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))