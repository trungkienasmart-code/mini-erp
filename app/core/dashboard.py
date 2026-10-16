# app/core/dashboard.py
"""Service tính toán số liệu cho Dashboard trang chủ."""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlmodel import Session, select, func, or_


def get_dashboard_stats(session: Session) -> dict:
    """Tính tất cả số liệu cho Dashboard."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start.replace(day=1)

    stats = {}

    # === 1. DOANH THU ===
    try:
        from app.modules.ban_hang.models import SaleOrder

        def revenue_between(d_from, d_to):
            result = session.exec(
                select(func.coalesce(func.sum(SaleOrder.total_amount), 0))
                .where(SaleOrder.created_at >= d_from)
                .where(SaleOrder.created_at <= d_to)
                .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
            ).one()
            return float(result or 0)

        stats["revenue_today"] = revenue_between(today_start, now)
        stats["revenue_week"] = revenue_between(week_start, now)
        stats["revenue_month"] = revenue_between(month_start, now)
    except Exception:
        stats["revenue_today"] = 0
        stats["revenue_week"] = 0
        stats["revenue_month"] = 0

    # === 2. ĐƠN HÀNG ===
    try:
        from app.modules.ban_hang.models import SaleOrder

        # Đơn bán chưa thanh toán
        unpaid_sales = session.exec(
            select(func.count()).select_from(SaleOrder)
            .where(SaleOrder.status.in_(["CONFIRMED", "PARTIAL"]))
        ).one() or 0
        stats["unpaid_sales"] = unpaid_sales

        # Đơn bán hôm nay
        orders_today = session.exec(
            select(func.count()).select_from(SaleOrder)
            .where(SaleOrder.created_at >= today_start)
        ).one() or 0
        stats["orders_today"] = orders_today
    except Exception:
        stats["unpaid_sales"] = 0
        stats["orders_today"] = 0

    try:
        from app.modules.mua_hang.models import PurchaseOrder

        # Đơn mua chờ duyệt
        draft_purchase = session.exec(
            select(func.count()).select_from(PurchaseOrder)
            .where(PurchaseOrder.status == "DRAFT")
        ).one() or 0
        stats["draft_purchase"] = draft_purchase

        # Đơn mua chờ nhận
        pending_purchase = session.exec(
            select(func.count()).select_from(PurchaseOrder)
            .where(PurchaseOrder.status == "APPROVED")
        ).one() or 0
        stats["pending_purchase"] = pending_purchase
    except Exception:
        stats["draft_purchase"] = 0
        stats["pending_purchase"] = 0

    # === 3. TỒN KHO THẤP ===
    try:
        from app.modules.quan_ly_kho.models import Product

        low_stock_products = session.exec(
            select(Product)
            .where(Product.stock_quantity <= Product.min_stock)
            .where(Product.min_stock > 0)
            .order_by(Product.stock_quantity)
            .limit(10)
        ).all()
        stats["low_stock"] = low_stock_products
        stats["low_stock_count"] = len(low_stock_products)
    except Exception:
        stats["low_stock"] = []
        stats["low_stock_count"] = 0

    # === 4. CÔNG NỢ ===
    try:
        from app.modules.ban_hang.models import Customer
        from app.modules.quan_ly_kho.models import Supplier

        stats["receivable"] = float(session.exec(
            select(func.coalesce(func.sum(Customer.current_debt), 0))
        ).one() or 0)
        stats["payable"] = float(session.exec(
            select(func.coalesce(func.sum(Supplier.current_debt), 0))
        ).one() or 0)
        stats["net_debt"] = stats["receivable"] - stats["payable"]
    except Exception:
        stats["receivable"] = 0
        stats["payable"] = 0
        stats["net_debt"] = 0

    # === 5. TOP SẢN PHẨM BÁN CHẠY (30 ngày) ===
    try:
        from app.modules.ban_hang.models import SaleOrder, SaleOrderLine
        from app.modules.quan_ly_kho.models import Product

        thirty_days = now - timedelta(days=30)
        results = session.exec(
            select(
                SaleOrderLine.product_id,
                func.sum(SaleOrderLine.base_quantity).label("total_qty"),
                func.sum(SaleOrderLine.line_total).label("total_revenue"),
            )
            .join(SaleOrder, SaleOrderLine.order_id == SaleOrder.id)
            .where(SaleOrder.created_at >= thirty_days)
            .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
            .group_by(SaleOrderLine.product_id)
            .order_by(func.sum(SaleOrderLine.base_quantity).desc())
            .limit(5)
        ).all()

        top_products = []
        for pid, qty, revenue in results:
            p = session.get(Product, pid)
            if p:
                top_products.append({
                    "product": p,
                    "quantity": int(qty or 0),
                    "revenue": float(revenue or 0),
                })
        stats["top_products"] = top_products
    except Exception:
        stats["top_products"] = []

    # === 5b. DOANH THU 7 NGÀY GẦN NHẤT (cho biểu đồ) ===
    try:
        from app.modules.ban_hang.models import SaleOrder
        revenue_7d = []
        for i in range(6, -1, -1):
            day_start = today_start - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            r = session.exec(
                select(func.coalesce(func.sum(SaleOrder.total_amount), 0))
                .where(SaleOrder.created_at >= day_start)
                .where(SaleOrder.created_at < day_end)
                .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
            ).one() or 0
            revenue_7d.append({
                "date": day_start.strftime("%d/%m"),
                "label": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"][day_start.weekday()],
                "value": float(r),
            })
        stats["revenue_7days"] = revenue_7d
        stats["revenue_7days_max"] = max([d["value"] for d in revenue_7d] + [1])
    except Exception:
        stats["revenue_7days"] = []
        stats["revenue_7days_max"] = 1


    # === 6. TIN TỨC MỚI ===
    try:
        from app.modules.tin_tuc.services import get_all_news, count_unread
        stats["news"] = get_all_news(session, limit=3)
        stats["news_unread"] = count_unread(session)
    except Exception:
        stats["news"] = []
        stats["news_unread"] = 0

    # === 7. TÀI SẢN (nếu admin) ===
    try:
        from app.modules.ke_toan.models import CashAccount
        total_cash = session.exec(
            select(func.coalesce(func.sum(CashAccount.current_balance), 0))
            .where(CashAccount.account_type == "CASH")
            .where(CashAccount.status == "ACTIVE")
        ).one() or 0
        total_bank = session.exec(
            select(func.coalesce(func.sum(CashAccount.current_balance), 0))
            .where(CashAccount.account_type == "BANK")
            .where(CashAccount.status == "ACTIVE")
        ).one() or 0
        stats["total_cash"] = float(total_cash)
        stats["total_bank"] = float(total_bank)
    except Exception:
        stats["total_cash"] = 0
        stats["total_bank"] = 0

    return stats
