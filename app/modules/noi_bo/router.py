# app/modules/noi_bo/router.py
from urllib.parse import quote
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import Session
from typing import Optional

from app.core.templates import templates
from app.core.database import get_session
from app.modules.auth.dependencies import require_login
from app.modules.auth import services as auth_services
from app.modules.noi_bo import services
from app.modules.noi_bo.schemas import (
    CategoryCreate, CategoryUpdate,
    PostCreate, PostUpdate, CommentCreate,
)

router = APIRouter(prefix="/internal", tags=["Internal"])


# ============================================================
# HELPERS
# ============================================================
def _get_user_role_codes(session: Session, user_id: int) -> list:
    """Lấy list role codes của user."""
    roles = auth_services.get_roles_of_user(session, user_id)
    return [r.code for r in roles]


def _can_edit_post(session: Session, user, post) -> bool:
    """Check user có quyền sửa bài viết không."""
    if not user or not post:
        return False
    # Admin hoặc author
    if auth_services.is_admin(session, user.id):
        return True
    if post.author_id == user.id:
        return True
    # Có quyền internal.post.edit
    if auth_services.has_permission(session, user.id, "internal.post.edit"):
        return True
    return False


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# FEED — TRANG CHÍNH
# ============================================================
@router.get("/")
def feed(
    request: Request,
    cat: str = "",
    post: str = "",
    q: str = "",
    tag: str = "",
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Trang bảng tin 3 cột."""
    # Lấy role codes của user
    role_codes = _get_user_role_codes(session, user.id)

    # Danh mục
    categories = services.get_all_categories(session)
    cat_id = int(cat) if cat.isdigit() else None

    # Đếm số bài viết chưa đọc cho mỗi category
    cat_stats = {}
    for c in categories:
        posts = services.get_all_posts(session, category_id=c.id,
                                        user_role_codes=role_codes)
        published = [p for p in posts if p.status == "PUBLISHED"]
        unread = sum(1 for p in published if not services.is_read(session, p.id, user.id))
        cat_stats[c.id] = {
            "total": len(published),
            "unread": unread,
        }

    # Lấy bài viết theo filter
    posts = services.get_all_posts(
        session,
        category_id=cat_id,
        keyword=q,
        tag=tag,
        user_role_codes=role_codes,
        limit=100,
    )

    # Nếu user chỉ có quyền view → chỉ thấy PUBLISHED
    can_create = auth_services.has_permission(session, user.id, "internal.post.create")
    if not can_create:
        posts = [p for p in posts if p.status == "PUBLISHED"]
    else:
        # Với người có quyền tạo: hiện cả DRAFT của chính họ + PUBLISHED
        posts = [p for p in posts if p.status == "PUBLISHED" or p.author_id == user.id]

    # Chi tiết bài viết (nếu có ?post=)
    current_post = None
    attachments = []
    comments = []
    readers = []
    acknowledgers = []
    is_read_flag = False
    has_ack = False
    can_edit = False

    post_id = int(post) if post.isdigit() else None
    if post_id:
        current_post = services.get_post(session, post_id)
        if current_post:
            # Đánh dấu đã đọc
            services.mark_as_read(session, post_id, user.id)
            services.increment_view_count(session, post_id)
            session.commit()

            attachments = services.get_attachments(session, post_id)
            comments = services.get_comments(session, post_id)
            readers = services.get_readers(session, post_id)

            # Kiểm tra category có require_read không
            cat = services.get_category(session, current_post.category_id)
            if cat and cat.is_require_read:
                has_ack = services.has_acknowledged(session, post_id, user.id)
                # Cho phép xem danh sách người đã ack nếu có quyền
                if auth_services.has_permission(session, user.id, "internal.post.edit") or \
                   auth_services.is_admin(session, user.id):
                    acknowledgers = services.get_acknowledgers(session, post_id)

            can_edit = _can_edit_post(session, user, current_post)

    # Pending acks (popup nhắc)
    pending_acks = services.get_pending_acks(session, user.id)

    # Stats
    stats = services.get_stats(session, user.id)

    return templates.TemplateResponse(
        request=request,
        name="noi_bo/feed.html",
        context={
            "user": user,
            "categories": categories,
            "cat_stats": cat_stats,
            "cat_id": cat_id,
            "current_post": current_post,
            "posts": posts,
            "attachments": attachments,
            "comments": comments,
            "readers": readers,
            "acknowledgers": acknowledgers,
            "has_ack": has_ack,
            "can_edit": can_edit,
            "can_create": can_create,
            "keyword": q,
            "tag": tag,
            "pending_acks": pending_acks,
            "stats": stats,
            "get_file_url": services.get_file_url,
            "format_file_size": services._format_file_size,
        },
    )


# ============================================================
# POST CRUD
# ============================================================
@router.get("/posts/new")
def post_new_form(
    request: Request,
    cat: str = "",
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.post.create"):
        return _redirect_with_msg("/internal/", "error", "Không có quyền tạo bài viết")

    categories = services.get_all_categories(session)
    default_cat_id = int(cat) if cat.isdigit() else (categories[0].id if categories else None)

    return templates.TemplateResponse(
        request=request,
        name="noi_bo/post_form.html",
        context={
            "user": user,
            "post": None,
            "categories": categories,
            "default_cat_id": default_cat_id,
            "is_edit": False,
        },
    )


@router.post("/posts/create")
def post_create(
    request: Request,
    category_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(""),
    status: str = Form("DRAFT"),
    is_pinned: str = Form(""),
    tags: str = Form(""),
    visibility: str = Form("ALL"),
    visible_role_codes: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.post.create"):
        return _redirect_with_msg("/internal/", "error", "Không có quyền")

    post, msg = services.create_post(
        session,
        PostCreate(
            category_id=category_id,
            title=title,
            content=content,
            status=status,
            is_pinned=is_pinned == "on",
            tags=tags,
            visibility=visibility,
            visible_role_codes=visible_role_codes,
        ),
        author_id=user.id,
        author_name=user.full_name,
    )

    if not post:
        return _redirect_with_msg(f"/internal/posts/new?cat={category_id}", "error", msg)

    # Audit
    auth_services.write_audit(
        session, user.id, "CREATE", "internal_post", post.id,
        new_value={"title": title, "status": status, "category_id": category_id},
        description=f"Tạo bài viết '{title}'",
        ip=request.client.host if request.client else "",
    )
    session.commit()

    return _redirect_with_msg(f"/internal/?cat={category_id}&post={post.id}",
                               "success", f"Đã tạo bài viết {post.code}")


@router.get("/posts/{pid}/edit")
def post_edit_form(
    pid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    post = services.get_post(session, pid)
    if not post:
        return _redirect_with_msg("/internal/", "error", "Bài viết không tồn tại")

    if not _can_edit_post(session, user, post):
        return _redirect_with_msg("/internal/", "error", "Không có quyền sửa bài viết này")

    categories = services.get_all_categories(session)
    attachments = services.get_attachments(session, pid)

    return templates.TemplateResponse(
        request=request,
        name="noi_bo/post_form.html",
        context={
            "user": user,
            "post": post,
            "categories": categories,
            "default_cat_id": post.category_id,
            "attachments": attachments,
            "is_edit": True,
            "get_file_url": services.get_file_url,
            "format_file_size": services._format_file_size,
        },
    )


@router.post("/posts/{pid}/update")
def post_update(
    pid: int, request: Request,
    category_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(""),
    status: str = Form("DRAFT"),
    is_pinned: str = Form(""),
    tags: str = Form(""),
    visibility: str = Form("ALL"),
    visible_role_codes: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    post = services.get_post(session, pid)
    if not post:
        return _redirect_with_msg("/internal/", "error", "Bài viết không tồn tại")

    if not _can_edit_post(session, user, post):
        return _redirect_with_msg("/internal/", "error", "Không có quyền")

    old_data = {"title": post.title, "status": post.status}

    updated, msg = services.update_post(session, pid, PostUpdate(
        category_id=category_id,
        title=title,
        content=content,
        status=status,
        is_pinned=is_pinned == "on",
        tags=tags,
        visibility=visibility,
        visible_role_codes=visible_role_codes,
    ))

    if not updated:
        return _redirect_with_msg(f"/internal/posts/{pid}/edit", "error", msg)

    auth_services.write_audit(
        session, user.id, "UPDATE", "internal_post", pid,
        old_value=old_data,
        new_value={"title": title, "status": status, "category_id": category_id},
        description=f"Cập nhật bài viết '{title}'",
        ip=request.client.host if request.client else "",
    )
    session.commit()

    return _redirect_with_msg(f"/internal/?cat={category_id}&post={pid}",
                               "success", "Đã cập nhật bài viết")


@router.post("/posts/{pid}/delete")
def post_delete(
    pid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    post = services.get_post(session, pid)
    if not post:
        return _redirect_with_msg("/internal/", "error", "Bài viết không tồn tại")

    if not _can_edit_post(session, user, post):
        return _redirect_with_msg("/internal/", "error", "Không có quyền xóa")

    title = post.title
    cat_id = post.category_id

    ok, msg = services.delete_post(session, pid)
    if ok:
        auth_services.write_audit(
            session, user.id, "DELETE", "internal_post", pid,
            old_value={"title": title},
            description=f"Xóa bài viết '{title}'",
            ip=request.client.host if request.client else "",
        )
        session.commit()

    return _redirect_with_msg(f"/internal/?cat={cat_id}",
                               "success" if ok else "error", msg)


# ============================================================
# UPLOAD FILE
# ============================================================
@router.post("/posts/{pid}/upload")
async def post_upload(
    pid: int, request: Request,
    file: UploadFile = File(...),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Upload file (AJAX)."""
    post = services.get_post(session, pid)
    if not post:
        return JSONResponse({"success": False, "message": "Bài viết không tồn tại"},
                             status_code=404)

    if not _can_edit_post(session, user, post):
        return JSONResponse({"success": False, "message": "Không có quyền"},
                             status_code=403)

    # Đọc nội dung file
    content = await file.read()

    att, msg = services.save_uploaded_file(
        session, pid,
        original_name=file.filename,
        file_content=content,
        content_type=file.content_type or "",
        user_id=user.id,
    )

    if not att:
        return JSONResponse({"success": False, "message": msg}, status_code=400)

    return JSONResponse({
        "success": True,
        "attachment": {
            "id": att.id,
            "original_name": att.original_name,
            "file_type": att.file_type,
            "file_size": att.file_size,
            "file_size_text": services._format_file_size(att.file_size),
            "url": services.get_file_url(att),
        },
    })


@router.post("/attachments/{aid}/delete")
def attachment_delete(
    aid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    att = services.get_attachment(session, aid)
    if not att:
        return JSONResponse({"success": False, "message": "File không tồn tại"},
                             status_code=404)

    post = services.get_post(session, att.post_id)
    if not post or not _can_edit_post(session, user, post):
        return JSONResponse({"success": False, "message": "Không có quyền"},
                             status_code=403)

    ok, msg = services.delete_attachment(session, aid)
    return JSONResponse({"success": ok, "message": msg})


# ============================================================
# COMMENT
# ============================================================
@router.post("/posts/{pid}/comment")
def post_comment(
    pid: int, request: Request,
    content: str = Form(...),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    post = services.get_post(session, pid)
    if not post:
        return _redirect_with_msg("/internal/", "error", "Bài viết không tồn tại")

    cmt, msg = services.create_comment(
        session,
        CommentCreate(post_id=pid, content=content),
        user_id=user.id,
        user_name=user.full_name,
    )

    if not cmt:
        return _redirect_with_msg(f"/internal/?cat={post.category_id}&post={pid}",
                                   "error", msg)

    return RedirectResponse(
        url=f"/internal/?cat={post.category_id}&post={pid}#comment-{cmt.id}",
        status_code=303,
    )


@router.post("/comments/{cid}/delete")
def comment_delete(
    cid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    from app.modules.noi_bo.models import InternalComment
    cmt = session.get(InternalComment, cid)
    if not cmt:
        return _redirect_with_msg("/internal/", "error", "Bình luận không tồn tại")

    post = services.get_post(session, cmt.post_id)

    # Chỉ author comment hoặc admin/người có quyền edit mới xóa được
    can_delete = (cmt.user_id == user.id) or \
                 auth_services.is_admin(session, user.id) or \
                 auth_services.has_permission(session, user.id, "internal.post.edit")

    if not can_delete:
        return _redirect_with_msg(f"/internal/?cat={post.category_id}&post={post.id}",
                                   "error", "Không có quyền xóa bình luận này")

    ok, msg = services.delete_comment(session, cid)

    return _redirect_with_msg(
        f"/internal/?cat={post.category_id}&post={post.id}",
        "success" if ok else "error", msg,
    )


# ============================================================
# ACKNOWLEDGE (Xác nhận đọc Nội quy)
# ============================================================
@router.post("/posts/{pid}/acknowledge")
def post_acknowledge(
    pid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    post = services.get_post(session, pid)
    if not post:
        return _redirect_with_msg("/internal/", "error", "Bài viết không tồn tại")

    services.acknowledge_post(session, pid, user.id)

    return RedirectResponse(
        url=f"/internal/?cat={post.category_id}&post={pid}",
        status_code=303,
    )


# ============================================================
# CATEGORY CRUD
# ============================================================
@router.get("/categories")
def category_list(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.category.manage"):
        return _redirect_with_msg("/internal/", "error",
                                   "Không có quyền quản lý danh mục")

    categories = services.get_all_categories(session)

    # Đếm bài viết trong mỗi danh mục
    cat_counts = {}
    for c in categories:
        posts = services.get_all_posts(session, category_id=c.id)
        cat_counts[c.id] = len(posts)

    return templates.TemplateResponse(
        request=request,
        name="noi_bo/category_list.html",
        context={
            "user": user,
            "categories": categories,
            "cat_counts": cat_counts,
        },
    )


@router.get("/categories/new")
def category_new_form(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.category.manage"):
        return _redirect_with_msg("/internal/", "error", "Không có quyền")

    return templates.TemplateResponse(
        request=request,
        name="noi_bo/category_form.html",
        context={"user": user, "category": None, "is_edit": False},
    )


@router.get("/categories/{cid}/edit")
def category_edit_form(
    cid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.category.manage"):
        return _redirect_with_msg("/internal/", "error", "Không có quyền")

    cat = services.get_category(session, cid)
    if not cat:
        return _redirect_with_msg("/internal/categories", "error", "Danh mục không tồn tại")

    return templates.TemplateResponse(
        request=request,
        name="noi_bo/category_form.html",
        context={"user": user, "category": cat, "is_edit": True},
    )


@router.post("/categories/create")
def category_create(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#6c757d"),
    icon: str = Form("bi-folder"),
    order_index: int = Form(0),
    is_require_read: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.category.manage"):
        return _redirect_with_msg("/internal/categories", "error", "Không có quyền")

    cat, msg = services.create_category(session, CategoryCreate(
        code=code.strip().upper(),
        name=name.strip(),
        description=description,
        color=color,
        icon=icon,
        order_index=order_index,
        is_require_read=is_require_read == "on",
    ))

    return _redirect_with_msg("/internal/categories",
                               "success" if cat else "error",
                               msg if not cat else f"Đã tạo danh mục {name}")


@router.post("/categories/{cid}/update")
def category_update(
    cid: int, request: Request,
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#6c757d"),
    icon: str = Form("bi-folder"),
    order_index: int = Form(0),
    is_require_read: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.category.manage"):
        return _redirect_with_msg("/internal/categories", "error", "Không có quyền")

    services.update_category(session, cid, CategoryUpdate(
        name=name.strip(),
        description=description,
        color=color,
        icon=icon,
        order_index=order_index,
        is_require_read=is_require_read == "on",
    ))

    return _redirect_with_msg("/internal/categories", "success", "Đã cập nhật danh mục")


@router.post("/categories/{cid}/delete")
def category_delete(
    cid: int, request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    if not auth_services.has_permission(session, user.id, "internal.category.manage"):
        return _redirect_with_msg("/internal/categories", "error", "Không có quyền")

    ok, msg = services.delete_category(session, cid)
    return _redirect_with_msg("/internal/categories",
                               "success" if ok else "error", msg)