# app/modules/noi_bo/schemas.py
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ CATEGORY ============
class CategoryCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    color: str = "#6c757d"
    icon: str = "bi-folder"
    order_index: int = 0
    is_require_read: bool = False


class CategoryUpdate(BaseModel):
    name: str
    description: str = ""
    color: str = "#6c757d"
    icon: str = "bi-folder"
    order_index: int = 0
    is_require_read: bool = False


# ============ POST ============
class PostCreate(BaseModel):
    category_id: int
    title: str
    content: str = ""
    status: str = "DRAFT"
    is_pinned: bool = False
    tags: str = ""
    visibility: str = "ALL"
    visible_role_codes: str = ""


class PostUpdate(PostCreate):
    pass


# ============ COMMENT ============
class CommentCreate(BaseModel):
    post_id: int
    content: str = Field(min_length=1, max_length=2000)