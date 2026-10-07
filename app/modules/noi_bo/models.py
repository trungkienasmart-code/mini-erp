# app/modules/noi_bo/models.py
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# DANH MỤC
# ============================================================
class InternalCategory(SQLModel, table=True):
    __tablename__ = "int_category"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=300)
    color: str = Field(default="#6c757d", max_length=20)
    icon: str = Field(default="bi-folder", max_length=50)
    order_index: int = Field(default=0)

    is_require_read: bool = Field(default=False)  # Bắt buộc đọc (cho Nội quy)
    is_system: bool = Field(default=False)  # Không cho xóa

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# BÀI VIẾT
# ============================================================
class InternalPost(SQLModel, table=True):
    __tablename__ = "int_post"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    category_id: int = Field(foreign_key="int_category.id", index=True)

    title: str = Field(max_length=300)
    content: str = Field(default="")  # TEXT

    status: str = Field(default="DRAFT", max_length=20)
    # DRAFT / PUBLISHED / ARCHIVED

    is_pinned: bool = Field(default=False)
    tags: str = Field(default="", max_length=300)  # CSV tags: "quan-trong,khan-cap"

    visibility: str = Field(default="ALL", max_length=20)  # ALL / ROLES
    visible_role_codes: str = Field(default="", max_length=500)  # CSV

    author_id: Optional[int] = Field(default=None, foreign_key="auth_user.id")
    author_name: str = Field(default="", max_length=100)

    view_count: int = Field(default=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = Field(default=None)

    # Relationships
    attachments: List["InternalAttachment"] = Relationship(
        back_populates="post",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    comments: List["InternalComment"] = Relationship(
        back_populates="post",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# ============================================================
# FILE ĐÍNH KÈM
# ============================================================
class InternalAttachment(SQLModel, table=True):
    __tablename__ = "int_attachment"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="int_post.id", index=True)

    original_name: str = Field(max_length=300)  # Tên gốc
    stored_name: str = Field(max_length=300)  # Tên trên disk
    file_path: str = Field(max_length=500)  # Đường dẫn tương đối
    file_size: int = Field(default=0)  # Bytes
    file_type: str = Field(default="OTHER", max_length=20)  # IMAGE/PDF/TEXT/OTHER
    mime_type: str = Field(default="", max_length=100)

    uploaded_by: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    post: Optional[InternalPost] = Relationship(back_populates="attachments")


# ============================================================
# BÌNH LUẬN
# ============================================================
class InternalComment(SQLModel, table=True):
    __tablename__ = "int_comment"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="int_post.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="auth_user.id")

    user_name: str = Field(default="", max_length=100)
    content: str = Field(max_length=2000)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    post: Optional[InternalPost] = Relationship(back_populates="comments")


# ============================================================
# ĐÃ ĐỌC
# ============================================================
class InternalReadLog(SQLModel, table=True):
    __tablename__ = "int_read_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="int_post.id", index=True)
    user_id: int = Field(foreign_key="auth_user.id", index=True)

    read_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# XÁC NHẬN ĐỌC (cho Nội quy bắt buộc đọc)
# ============================================================
class InternalAck(SQLModel, table=True):
    __tablename__ = "int_ack"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="int_post.id", index=True)
    user_id: int = Field(foreign_key="auth_user.id", index=True)

    ack_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))