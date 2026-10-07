# app/modules/noi_bo/services.py
import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from sqlmodel import Session, select, or_, func

from app.core.config import BASE_DIR
from app.modules.noi_bo.models import (
    InternalCategory, InternalPost, InternalAttachment,
    InternalComment, InternalReadLog, InternalAck,
)
from app.modules.noi_bo.schemas import (
    CategoryCreate, CategoryUpdate,
    PostCreate, PostUpdate, CommentCreate,
)


# ============================================================
# CONSTANTS
# ============================================================
UPLOAD_DIR = BASE_DIR / "app" / "static" / "uploads" / "internal"
UPLOAD_URL_PREFIX = "/static/uploads/internal"

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = {
    # Images
    "image/jpeg": "IMAGE",
    "image/png": "IMAGE",
    "image/gif": "IMAGE",
    "image/webp": "IMAGE",
    # Documents
    "application/pdf": "PDF",
    # Text
    "text/plain": "TEXT",
    "text/csv": "TEXT",
}

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".txt", ".csv",
}


def _ensure_upload_dir():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _detect_file_type(filename: str, content_type: str) -> str:
    """Xác định loại file từ content type."""
    if content_type in ALLOWED_MIME_TYPES:
        return ALLOWED_MIME_TYPES[content_type]
    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return "IMAGE"
    if ext == ".pdf":
        return "PDF"
    if ext in (".txt", ".csv"):
        return "TEXT"
    return "OTHER"


def _format_file_size(size: int) -> str:
    """Format size cho template."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} TB"


# ============================================================
# CATEGORY
# ============================================================
def get_all_categories(session: Session) -> List[InternalCategory]:
    return list(session.exec(
        select(InternalCategory).order_by(
            InternalCategory.order_index, InternalCategory.name
        )
    ).all())


def get_category(session: Session, cid: int) -> Optional[InternalCategory]:
    return session.get(InternalCategory, cid)


def create_category(session: Session, data: CategoryCreate) -> Tuple[Optional[InternalCategory], str]:
    try:
        existing = session.exec(
            select(InternalCategory).where(InternalCategory.code == data.code)
        ).first()
        if existing:
            return None, f"Mã danh mục '{data.code}' đã tồn tại"

        cat = InternalCategory(**data.model_dump())
        session.add(cat)
        session.commit()
        session.refresh(cat)
        return cat, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi: {e}"


def update_category(session: Session, cid: int, data: CategoryUpdate) -> Optional[InternalCategory]:
    cat = session.get(InternalCategory, cid)
    if not cat:
        return None
    for k, v in data.model_dump().items():
        setattr(cat, k, v)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def delete_category(session: Session, cid: int) -> Tuple[bool, str]:
    cat = session.get(InternalCategory, cid)
    if not cat:
        return False, "Danh mục không tồn tại"
    if cat.is_system:
        return False, "Không thể xóa danh mục hệ thống"

    # Check có bài viết không
    post_count = session.exec(
        select(func.count()).select_from(InternalPost)
        .where(InternalPost.category_id == cid)
    ).one() or 0
    if post_count > 0:
        return False, f"Có {post_count} bài viết đang dùng danh mục này"

    session.delete(cat)
    session.commit()
    return True, "Đã xóa danh mục"


# ============================================================
# POST
# ============================================================
def _gen_post_code(session: Session) -> str:
    """Sinh mã bài viết: NB + YYMMDD + STT."""
    today = datetime.now().strftime("%y%m%d")
    pattern = f"NB{today}%"
    count = session.exec(
        select(func.count()).select_from(InternalPost)
        .where(InternalPost.code.like(pattern))
    ).one() or 0
    return f"NB{today}{count + 1:04d}"


def get_all_posts(
    session: Session,
    category_id: Optional[int] = None,
    keyword: str = "",
    tag: str = "",
    status: str = "",
    user_role_codes: List[str] = None,
    limit: int = 100,
) -> List[InternalPost]:
    """
    Lấy DS bài viết với filter.
    - user_role_codes: để filter bài chỉ hiển thị cho 1 số role.
    """
    stmt = select(InternalPost)

    if category_id:
        stmt = stmt.where(InternalPost.category_id == category_id)

    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(or_(
            InternalPost.title.like(p),
            InternalPost.content.like(p),
        ))

    if tag:
        # Tag là CSV: "quan-trong,khan-cap"
        p = f"%{tag.strip()}%"
        stmt = stmt.where(InternalPost.tags.like(p))

    if status:
        stmt = stmt.where(InternalPost.status == status)
    else:
        # Mặc định chỉ lấy PUBLISHED (trừ khi user là tác giả/admin)
        stmt = stmt.where(InternalPost.status.in_(["PUBLISHED", "DRAFT"]))

    # Sắp xếp: pinned trước, rồi theo created_at desc
    stmt = stmt.order_by(
        InternalPost.is_pinned.desc(),
        InternalPost.created_at.desc(),
    ).limit(limit)

    posts = list(session.exec(stmt).all())

    # Filter visibility=ROLES
    if user_role_codes is not None:
        result = []
        for p in posts:
            if p.visibility == "ALL":
                result.append(p)
            elif p.visibility == "ROLES":
                allowed = [r.strip() for r in (p.visible_role_codes or "").split(",") if r.strip()]
                if any(r in user_role_codes for r in allowed):
                    result.append(p)
        return result

    return posts


def get_post(session: Session, pid: int) -> Optional[InternalPost]:
    return session.get(InternalPost, pid)


def create_post(
    session: Session, data: PostCreate,
    author_id: Optional[int] = None, author_name: str = "",
) -> Tuple[Optional[InternalPost], str]:
    try:
        code = _gen_post_code(session)
        post = InternalPost(
            code=code,
            category_id=data.category_id,
            title=data.title.strip(),
            content=data.content,
            status=data.status,
            is_pinned=data.is_pinned,
            tags=data.tags,
            visibility=data.visibility,
            visible_role_codes=data.visible_role_codes,
            author_id=author_id,
            author_name=author_name,
            published_at=datetime.now(timezone.utc) if data.status == "PUBLISHED" else None,
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        return post, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi: {e}"


def update_post(
    session: Session, pid: int, data: PostUpdate,
) -> Tuple[Optional[InternalPost], str]:
    try:
        post = session.get(InternalPost, pid)
        if not post:
            return None, "Bài viết không tồn tại"

        old_status = post.status
        for k, v in data.model_dump().items():
            setattr(post, k, v)
        post.updated_at = datetime.now(timezone.utc)

        # Nếu chuyển từ DRAFT → PUBLISHED lần đầu
        if old_status != "PUBLISHED" and data.status == "PUBLISHED":
            post.published_at = datetime.now(timezone.utc)

        session.add(post)
        session.commit()
        session.refresh(post)
        return post, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi: {e}"


def delete_post(session: Session, pid: int) -> Tuple[bool, str]:
    post = session.get(InternalPost, pid)
    if not post:
        return False, "Bài viết không tồn tại"

    # Xóa files trên disk
    atts = session.exec(
        select(InternalAttachment).where(InternalAttachment.post_id == pid)
    ).all()
    for att in atts:
        try:
            file_path = Path(att.file_path)
            if file_path.exists() and str(file_path).startswith(str(UPLOAD_DIR)):
                file_path.unlink()
        except Exception as e:
            print(f"[WARN] Không xóa được file {att.file_path}: {e}")

    # Xóa comments, reads, acks
    for cmt in session.exec(select(InternalComment).where(InternalComment.post_id == pid)).all():
        session.delete(cmt)
    for rl in session.exec(select(InternalReadLog).where(InternalReadLog.post_id == pid)).all():
        session.delete(rl)
    for ack in session.exec(select(InternalAck).where(InternalAck.post_id == pid)).all():
        session.delete(ack)
    for att in atts:
        session.delete(att)

    session.delete(post)
    session.commit()
    return True, "Đã xóa bài viết"


def increment_view_count(session: Session, pid: int):
    """Tăng view count (không cần commit riêng, gọi trong session)."""
    post = session.get(InternalPost, pid)
    if post:
        post.view_count += 1
        session.add(post)


# ============================================================
# ATTACHMENT
# ============================================================
def save_uploaded_file(
    session: Session, post_id: int,
    original_name: str, file_content: bytes,
    content_type: str, user_id: Optional[int] = None,
) -> Tuple[Optional[InternalAttachment], str]:
    """Lưu file lên disk + tạo record DB."""
    try:
        # Validate size
        if len(file_content) > MAX_FILE_SIZE:
            return None, f"File vượt quá {_format_file_size(MAX_FILE_SIZE)}"

        # Validate extension
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return None, f"Định dạng {ext} không được hỗ trợ. Chỉ cho phép: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

        # Tạo tên file unique
        _ensure_upload_dir()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR / unique_name

        # Ghi file
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Tạo record
        file_type = _detect_file_type(original_name, content_type)
        att = InternalAttachment(
            post_id=post_id,
            original_name=original_name,
            stored_name=unique_name,
            file_path=str(file_path),
            file_size=len(file_content),
            file_type=file_type,
            mime_type=content_type,
            uploaded_by=user_id,
        )
        session.add(att)
        session.commit()
        session.refresh(att)
        return att, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi lưu file: {e}"


def get_attachments(session: Session, post_id: int) -> List[InternalAttachment]:
    return list(session.exec(
        select(InternalAttachment)
        .where(InternalAttachment.post_id == post_id)
        .order_by(InternalAttachment.created_at)
    ).all())


def get_attachment(session: Session, aid: int) -> Optional[InternalAttachment]:
    return session.get(InternalAttachment, aid)


def delete_attachment(session: Session, aid: int) -> Tuple[bool, str]:
    att = session.get(InternalAttachment, aid)
    if not att:
        return False, "File không tồn tại"

    # Xóa file trên disk
    try:
        file_path = Path(att.file_path)
        if file_path.exists() and str(file_path).startswith(str(UPLOAD_DIR)):
            file_path.unlink()
    except Exception as e:
        print(f"[WARN] Không xóa được file: {e}")

    session.delete(att)
    session.commit()
    return True, "Đã xóa file"


def get_file_url(att: InternalAttachment) -> str:
    """Trả về URL để user truy cập file."""
    return f"{UPLOAD_URL_PREFIX}/{att.stored_name}"


# ============================================================
# COMMENT
# ============================================================
def get_comments(session: Session, post_id: int) -> List[InternalComment]:
    return list(session.exec(
        select(InternalComment)
        .where(InternalComment.post_id == post_id)
        .order_by(InternalComment.created_at)
    ).all())


def create_comment(
    session: Session, data: CommentCreate,
    user_id: Optional[int] = None, user_name: str = "",
) -> Tuple[Optional[InternalComment], str]:
    try:
        cmt = InternalComment(
            post_id=data.post_id,
            user_id=user_id,
            user_name=user_name,
            content=data.content.strip(),
        )
        session.add(cmt)
        session.commit()
        session.refresh(cmt)
        return cmt, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi: {e}"


def delete_comment(session: Session, cid: int) -> Tuple[bool, str]:
    cmt = session.get(InternalComment, cid)
    if not cmt:
        return False, "Bình luận không tồn tại"
    session.delete(cmt)
    session.commit()
    return True, "Đã xóa bình luận"


# ============================================================
# READ LOG
# ============================================================
def mark_as_read(session: Session, post_id: int, user_id: int):
    """Đánh dấu đã đọc. Idempotent."""
    existing = session.exec(
        select(InternalReadLog)
        .where(InternalReadLog.post_id == post_id)
        .where(InternalReadLog.user_id == user_id)
    ).first()
    if not existing:
        session.add(InternalReadLog(post_id=post_id, user_id=user_id))
        session.commit()


def get_readers(session: Session, post_id: int) -> List[InternalReadLog]:
    """Lấy DS user đã đọc bài viết."""
    return list(session.exec(
        select(InternalReadLog)
        .where(InternalReadLog.post_id == post_id)
        .order_by(InternalReadLog.read_at.desc())
    ).all())


def is_read(session: Session, post_id: int, user_id: int) -> bool:
    existing = session.exec(
        select(InternalReadLog)
        .where(InternalReadLog.post_id == post_id)
        .where(InternalReadLog.user_id == user_id)
    ).first()
    return existing is not None


# ============================================================
# ACK (Xác nhận đọc - cho Nội quy)
# ============================================================
def acknowledge_post(session: Session, post_id: int, user_id: int):
    """User xác nhận đã đọc bài viết bắt buộc."""
    existing = session.exec(
        select(InternalAck)
        .where(InternalAck.post_id == post_id)
        .where(InternalAck.user_id == user_id)
    ).first()
    if not existing:
        session.add(InternalAck(post_id=post_id, user_id=user_id))
        session.commit()


def has_acknowledged(session: Session, post_id: int, user_id: int) -> bool:
    existing = session.exec(
        select(InternalAck)
        .where(InternalAck.post_id == post_id)
        .where(InternalAck.user_id == user_id)
    ).first()
    return existing is not None


def get_pending_acks(session: Session, user_id: int) -> List[InternalPost]:
    """
    Lấy DS bài viết ở danh mục "bắt buộc đọc" mà user CHƯA xác nhận.
    Dùng để hiện popup nhắc nhở.
    """
    # Lấy các danh mục require read
    cats = session.exec(
        select(InternalCategory).where(InternalCategory.is_require_read == True)
    ).all()
    cat_ids = [c.id for c in cats]
    if not cat_ids:
        return []

    # Lấy posts đã published ở các category đó
    posts = session.exec(
        select(InternalPost)
        .where(InternalPost.category_id.in_(cat_ids))
        .where(InternalPost.status == "PUBLISHED")
    ).all()

    # Lọc bỏ posts đã ack
    acked_ids = set()
    for ack in session.exec(
        select(InternalAck).where(InternalAck.user_id == user_id)
    ).all():
        acked_ids.add(ack.post_id)

    return [p for p in posts if p.id not in acked_ids]


def get_acknowledgers(session: Session, post_id: int) -> List[InternalAck]:
    """DS user đã xác nhận (cho quản lý xem)."""
    return list(session.exec(
        select(InternalAck)
        .where(InternalAck.post_id == post_id)
        .order_by(InternalAck.ack_at.desc())
    ).all())


# ============================================================
# STATS
# ============================================================
def get_stats(session: Session, user_id: int) -> dict:
    """Thống kê cho dashboard."""
    total_posts = session.exec(
        select(func.count()).select_from(InternalPost)
        .where(InternalPost.status == "PUBLISHED")
    ).one() or 0

    total_categories = session.exec(
        select(func.count()).select_from(InternalCategory)
    ).one() or 0

    unread_count = 0
    posts = session.exec(
        select(InternalPost).where(InternalPost.status == "PUBLISHED")
    ).all()
    for p in posts:
        if not is_read(session, p.id, user_id):
            unread_count += 1

    pending_acks = len(get_pending_acks(session, user_id))

    return {
        "total_posts": total_posts,
        "total_categories": total_categories,
        "unread_count": unread_count,
        "pending_acks": pending_acks,
    }