# app/modules/tin_tuc/schemas.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AppNewsCreate(BaseModel):
    external_id: str = ""
    title: str
    summary: str = ""
    content: str = ""
    news_type: str = "FEATURE"
    version: str = ""
    priority: str = "NORMAL"
    action_url: str = ""
    action_label: str = ""
    is_pinned: bool = False
    published_at: Optional[datetime] = None