# app/modules/tin_tuc/router.py
from urllib.parse import quote
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import Session

from app.core.templates import templates
from app.core.database import get_session
from app.modules.auth.dependencies import require_login
from app.modules.tin_tuc import services

router = APIRouter(prefix="/app-news", tags=["App News"])


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# DANH SÁCH TIN
# ============================================================
@router.get("/")
def news_list(
    request: Request,
    news_id: str = "",
    unread: str = "",
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Trang DS tin + chi tiết."""
    only_unread = unread == "1"
    news_all = services.get_all_news(session, only_unread=only_unread, limit=100)
    unread_count = services.count_unread(session)

    # Nếu có news_id → xem chi tiết
    current_news = None
    news_id_int = None
    if news_id:
        try:
            news_id_int = int(news_id)
        except ValueError:
            pass

    if news_id_int:
        current_news = services.get_news(session, news_id_int)
        if current_news and not current_news.is_read:
            services.mark_as_read(session, current_news.id)
            current_news.is_read = True

    # Nếu không có news_id nhưng có tin → chọn tin đầu tiên
    if not current_news and news_all:
        current_news = news_all[0]
        if not current_news.is_read:
            services.mark_as_read(session, current_news.id)
            current_news.is_read = True

    return templates.TemplateResponse(
        request=request,
        name="tin_tuc/news_list.html",
        context={
            "user": user,
            "news_all": news_all,
            "current_news": current_news,
            "unread_count": unread_count,
            "only_unread": only_unread,
        },
    )


# ============================================================
# ĐÁNH DẤU ĐÃ ĐỌC TẤT CẢ
# ============================================================
@router.post("/mark-all-read")
def mark_all_read(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    services.mark_all_as_read(session)
    return _redirect_with_msg("/app-news/", "success", "Đã đánh dấu đọc tất cả")


# ============================================================
# SYNC TỪ SERVER (thủ công)
# ============================================================
@router.post("/sync")
def sync_news(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    count, msg = services.sync_from_server(session)
    return _redirect_with_msg(
        "/app-news/",
        "success" if count > 0 else "warning",
        msg,
    )


# ============================================================
# API — Lấy tin mới (cho navbar badge)
# ============================================================
@router.get("/api/unread-count")
def unread_count_api(
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    return JSONResponse({"count": services.count_unread(session)})


@router.get("/api/recent")
def recent_news_api(
    limit: int = 5,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    news = services.get_all_news(session, limit=limit)
    return JSONResponse({
        "news": [
            {
                "id": n.id,
                "title": n.title,
                "summary": n.summary,
                "news_type": n.news_type,
                "is_read": n.is_read,
                "is_pinned": n.is_pinned,
                "priority": n.priority,
                "published_at": n.published_at.isoformat() if n.published_at else None,
            }
            for n in news
        ],
    })
    