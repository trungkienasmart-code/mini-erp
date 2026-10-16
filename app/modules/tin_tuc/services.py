# app/modules/tin_tuc/services.py
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlmodel import Session, select, func

from app.modules.tin_tuc.models import AppNews
from app.modules.tin_tuc.schemas import AppNewsCreate


# ============================================================
# CẤU HÌNH SERVER GỐC (của bạn)
# ============================================================
NEWS_SERVER_URL = "https://api.apptinhgon.vn/news"
# ⚠️ Đổi URL khi bạn deploy server. Trước mắt để placeholder.
SYNC_TIMEOUT = 5  # seconds


# ============================================================
# QUERY
# ============================================================
def get_all_news(
    session: Session,
    only_unread: bool = False,
    limit: int = 50,
) -> List[AppNews]:
    stmt = select(AppNews)
    if only_unread:
        stmt = stmt.where(AppNews.is_read == False)
    stmt = stmt.order_by(
        AppNews.is_pinned.desc(),
        AppNews.published_at.desc(),
        AppNews.created_at.desc(),
    ).limit(limit)
    return list(session.exec(stmt).all())


def get_news(session: Session, nid: int) -> Optional[AppNews]:
    return session.get(AppNews, nid)


def count_unread(session: Session) -> int:
    return session.exec(
        select(func.count()).select_from(AppNews)
        .where(AppNews.is_read == False)
    ).one() or 0


# ============================================================
# CRUD
# ============================================================
def create_news(session: Session, data: AppNewsCreate) -> AppNews:
    news = AppNews(
        external_id=data.external_id,
        title=data.title,
        summary=data.summary,
        content=data.content,
        news_type=data.news_type,
        version=data.version,
        priority=data.priority,
        action_url=data.action_url,
        action_label=data.action_label,
        is_pinned=data.is_pinned,
        published_at=data.published_at or datetime.now(timezone.utc),
    )
    session.add(news)
    session.commit()
    session.refresh(news)
    return news


def mark_as_read(session: Session, nid: int):
    news = session.get(AppNews, nid)
    if news:
        news.is_read = True
        session.add(news)
        session.commit()


def mark_all_as_read(session: Session):
    news_list = session.exec(
        select(AppNews).where(AppNews.is_read == False)
    ).all()
    for n in news_list:
        n.is_read = True
        session.add(n)
    session.commit()


def delete_news(session: Session, nid: int) -> bool:
    news = session.get(AppNews, nid)
    if not news:
        return False
    session.delete(news)
    session.commit()
    return True


# ============================================================
# SYNC TỪ SERVER GỐC
# ============================================================
def sync_from_server(session: Session) -> Tuple[int, str]:
    """
    Pull tin mới từ server App Tinh Gọn.
    - Gọi GET {NEWS_SERVER_URL}?since={last_external_id}
    - Insert những tin chưa có (theo external_id).
    """
    try:
        # Lấy external_id lớn nhất đã có
        last_news = session.exec(
            select(AppNews)
            .where(AppNews.external_id != "")
            .order_by(AppNews.id.desc())
            .limit(1)
        ).first()

        since_id = last_news.external_id if last_news else ""

        # Gọi API
        url = NEWS_SERVER_URL
        if since_id:
            url += f"?since={since_id}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "MiniERP/1.0",
            "Accept": "application/json",
        })

        with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = data.get("news", []) if isinstance(data, dict) else data

        new_count = 0
        for item in items:
            ext_id = str(item.get("external_id") or item.get("id") or "").strip()
            if not ext_id:
                continue

            # Check tồn tại
            existing = session.exec(
                select(AppNews).where(AppNews.external_id == ext_id)
            ).first()
            if existing:
                continue

            # Parse published_at
            pub_at = None
            if item.get("published_at"):
                try:
                    pub_at = datetime.fromisoformat(
                        item["published_at"].replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            news = AppNews(
                external_id=ext_id,
                title=item.get("title", "")[:300],
                summary=item.get("summary", "")[:500],
                content=item.get("content", ""),
                news_type=item.get("news_type", "FEATURE"),
                version=item.get("version", ""),
                priority=item.get("priority", "NORMAL"),
                action_url=item.get("action_url", ""),
                action_label=item.get("action_label", ""),
                is_pinned=bool(item.get("is_pinned", False)),
                published_at=pub_at or datetime.now(timezone.utc),
            )
            session.add(news)
            new_count += 1

        session.commit()
        return new_count, f"Đã tải {new_count} tin mới"

    except urllib.error.URLError as e:
        return 0, f"Không kết nối được server: {e}"
    except Exception as e:
        return 0, f"Lỗi: {e}"


# ============================================================
# SEED SAMPLE NEWS (cho demo)
# ============================================================
def seed_sample_news(session: Session):
    """Tạo vài tin mẫu khi DB trống (để test)."""
    existing = session.exec(select(AppNews)).first()
    if existing:
        return

    samples = [
        AppNewsCreate(
            external_id="welcome-v1",
            title="Chào mừng bạn đến với App Tinh Gọn! 🎉",
            summary="Cảm ơn bạn đã tin dùng phần mềm quản lý dành cho Hộ kinh doanh.",
            content=(
                "Chào mừng bạn đến với Mini ERP — giải pháp quản lý tối ưu cho "
                "doanh nghiệp siêu nhỏ và hộ kinh doanh.\n\n"
                "Các tính năng chính:\n"
                "• POS bán hàng nhanh\n"
                "• Quản lý kho thông minh (FIFO/LIFO)\n"
                "• Kế toán HKD theo TT152/2025\n"
                "• Backup tự động\n"
                "• Hỗ trợ nhiều máy trong mạng LAN\n\n"
                "Nếu cần hỗ trợ, liên hệ Zalo: 0916.887.359"
            ),
            news_type="ANNOUNCEMENT",
            version="v1.0.0",
            priority="NORMAL",
            is_pinned=True,
        ),
        AppNewsCreate(
            external_id="feature-v1.1",
            title="Tính năng mới sắp ra mắt: Import Excel hàng loạt",
            summary="Import sản phẩm, NCC, đơn mua hàng từ file Excel trong vài giây.",
            content=(
                "Sắp tới, bạn sẽ có thể import hàng trăm sản phẩm cùng lúc từ file Excel.\n\n"
                "Lợi ích:\n"
                "• Tiết kiệm thời gian nhập liệu\n"
                "• Không lo sai sót\n"
                "• Có preview trước khi import\n\n"
                "Tính năng miễn phí cho tất cả người dùng."
            ),
            news_type="FEATURE",
            version="v1.1.0",
            priority="NORMAL",
        ),
        AppNewsCreate(
            external_id="module-crm",
            title="Module CRM — Quản lý khách hàng chuyên nghiệp",
            summary="Chăm sóc KH, tích điểm, gửi SMS/Email tự động.",
            content=(
                "Module CRM mở rộng giúp bạn:\n\n"
                "• Phân loại KH: VIP, thường, mới\n"
                "• Tích điểm đổi quà\n"
                "• Gửi SMS chúc mừng sinh nhật\n"
                "• Xem lịch sử mua hàng chi tiết\n"
                "• Báo cáo KH thân thiết\n\n"
                "💰 Giá: 1,500,000đ/năm (đang khuyến mãi 50% còn 750,000đ)\n\n"
                "Liên hệ Zalo để được tư vấn."
            ),
            news_type="MODULE",
            version="v2.0.0",
            priority="HIGH",
            action_url="https://zalo.me/0916887359",
            action_label="Liên hệ mua ngay",
        ),
    ]

    for s in samples:
        create_news(session, s)