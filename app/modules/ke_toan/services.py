# app/modules/ke_toan/services.py
from datetime import datetime, timezone, date, timedelta
from typing import List, Optional, Tuple, Dict
from calendar import monthrange

from sqlmodel import Session, select, func, or_

from app.modules.ke_toan.models import (
    HKDProfile, CashAccount, Voucher,
    FixedAsset, AssetDepreciation, PeriodLock,
)
from app.modules.ke_toan.schemas import (
    HKDProfileCreate, HKDProfileUpdate,
    CashAccountCreate, CashAccountUpdate,
    VoucherCreate,
    FixedAssetCreate, FixedAssetUpdate, AssetDisposal,
    PeriodLockCreate,
)


# ============================================================
# HELPERS
# ============================================================
def _gen_code(session: Session, model, prefix: str, length: int = 4) -> str:
    """Sinh mã tự động: PREFIX + STT."""
    stmt = select(func.count()).select_from(model)
    count = session.exec(stmt).one() or 0
    return f"{prefix}{count + 1:0{length}d}"


def _to_date(d) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").date()
    except ValueError:
        return None


# ============================================================
# HKD PROFILE
# ============================================================
def get_hkd_profile(session: Session) -> Optional[HKDProfile]:
    """Lấy cấu hình HKD (chỉ có 1 record duy nhất)."""
    return session.exec(select(HKDProfile)).first()


def create_or_update_hkd_profile(session: Session, data: HKDProfileCreate) -> HKDProfile:
    """Tạo hoặc cập nhật cấu hình HKD."""
    profile = get_hkd_profile(session)
    if profile:
        for k, v in data.model_dump().items():
            setattr(profile, k, v)
        profile.updated_at = datetime.now(timezone.utc)
    else:
        profile = HKDProfile(**data.model_dump())
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


# ============================================================
# PERIOD LOCK
# ============================================================
def get_locked_months(session: Session) -> List[str]:
    """Lấy danh sách tháng đã khóa."""
    locks = session.exec(
        select(PeriodLock).where(PeriodLock.status == "CLOSED")
    ).all()
    return [p.period for p in locks]


def is_period_locked(session: Session, period: str) -> bool:
    """Kiểm tra tháng đã khóa chưa."""
    lock = session.exec(
        select(PeriodLock)
        .where(PeriodLock.period == period)
        .where(PeriodLock.status == "CLOSED")
    ).first()
    return lock is not None


def lock_period(session: Session, data: PeriodLockCreate, user_id: Optional[int] = None) -> Tuple[bool, str]:
    """Khóa kỳ kế toán."""
    existing = session.exec(
        select(PeriodLock).where(PeriodLock.period == data.period)
    ).first()
    if existing:
        if existing.status == "CLOSED":
            return False, f"Kỳ {data.period} đã khóa rồi"
        existing.status = "CLOSED"
        existing.closed_at = datetime.now(timezone.utc)
        existing.closed_by = user_id
        existing.note = data.note
        session.add(existing)
    else:
        lock = PeriodLock(
            period=data.period,
            status="CLOSED",
            closed_at=datetime.now(timezone.utc),
            closed_by=user_id,
            note=data.note,
        )
        session.add(lock)
    session.commit()
    return True, f"Đã khóa kỳ {data.period}"


def unlock_period(session: Session, period: str) -> Tuple[bool, str]:
    """Mở khóa kỳ."""
    existing = session.exec(
        select(PeriodLock).where(PeriodLock.period == period)
    ).first()
    if not existing:
        return False, f"Kỳ {period} chưa khóa"
    session.delete(existing)
    session.commit()
    return True, f"Đã mở khóa kỳ {period}"


def get_all_period_locks(session: Session) -> List[PeriodLock]:
    return list(session.exec(
        select(PeriodLock).order_by(PeriodLock.period.desc())
    ).all())


# ============================================================
# CASH ACCOUNT
# ============================================================
def get_all_cash_accounts(session: Session, only_active: bool = False) -> List[CashAccount]:
    stmt = select(CashAccount)
    if only_active:
        stmt = stmt.where(CashAccount.status == "ACTIVE")
    stmt = stmt.order_by(CashAccount.code)
    return list(session.exec(stmt).all())


def get_cash_account(session: Session, cid: int) -> Optional[CashAccount]:
    return session.get(CashAccount, cid)


def create_cash_account(session: Session, data: CashAccountCreate) -> CashAccount:
    acc = CashAccount(**data.model_dump())
    acc.current_balance = data.opening_balance  # Ban đầu = số dư đầu kỳ
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


def update_cash_account(session: Session, cid: int, data: CashAccountUpdate) -> Optional[CashAccount]:
    acc = session.get(CashAccount, cid)
    if not acc:
        return None
    # Chỉ cho sửa các trường không ảnh hưởng số dư
    acc.code = data.code
    acc.name = data.name
    acc.bank_name = data.bank_name
    acc.bank_account_no = data.bank_account_no
    acc.bank_branch = data.bank_branch
    acc.note = data.note
    acc.status = data.status
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


def delete_cash_account(session: Session, cid: int) -> Tuple[bool, str]:
    acc = session.get(CashAccount, cid)
    if not acc:
        return False, "Tài khoản quỹ không tồn tại"
    # Kiểm tra có giao dịch không
    has_vouchers = session.exec(
        select(Voucher).where(Voucher.cash_account_id == cid)
    ).first()
    if has_vouchers:
        return False, "Không thể xóa: Đã có phiếu thu/chi dùng tài khoản này"
    session.delete(acc)
    session.commit()
    return True, "Đã xóa tài khoản quỹ"


# ============================================================
# VOUCHER (PHIẾU THU / CHI)
# ============================================================
def create_voucher(session: Session, data: VoucherCreate, user_id: Optional[int] = None) -> Tuple[Optional[Voucher], str]:
    """Tạo phiếu thu/chi, tự động cập nhật số dư quỹ."""
    try:
        acc = session.get(CashAccount, data.cash_account_id)
        if not acc:
            return None, "Tài khoản quỹ không tồn tại"
        if acc.status != "ACTIVE":
            return None, "Tài khoản quỹ đã ngừng hoạt động"

        # Ngày chứng từ
        v_date = data.voucher_date or datetime.now(timezone.utc).date()

        # Kiểm tra kỳ có bị khóa không
        period = v_date.strftime("%Y-%m")
        if is_period_locked(session, period):
            return None, f"Kỳ {period} đã bị khóa, không thể tạo phiếu"

        # Sinh mã
        prefix = "PT" if data.voucher_type == "RECEIPT" else "PC"
        code = _gen_code(session, Voucher, prefix, length=5)

        # Tạo voucher
        voucher = Voucher(
            code=code,
            voucher_type=data.voucher_type,
            cash_account_id=data.cash_account_id,
            partner_type=data.partner_type,
            partner_id=data.partner_id,
            partner_name=data.partner_name,
            amount=data.amount,
            category=data.category,
            reason=data.reason,
            note=data.note,
            ref_type=data.ref_type,
            ref_id=data.ref_id,
            voucher_date=v_date,
            user_id=user_id,
        )
        session.add(voucher)

        # Cập nhật số dư
        if data.voucher_type == "RECEIPT":
            acc.current_balance += data.amount
        else:  # PAYMENT
            if acc.current_balance < data.amount:
                session.rollback()
                return None, f"Số dư quỹ không đủ. Hiện có {acc.current_balance:,.0f}đ"
            acc.current_balance -= data.amount
        session.add(acc)

        session.commit()
        session.refresh(voucher)
        return voucher, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo phiếu: {e}"


def get_all_vouchers(
    session: Session,
    voucher_type: str = "",
    cash_account_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 500,
) -> List[Voucher]:
    stmt = select(Voucher)
    if voucher_type:
        stmt = stmt.where(Voucher.voucher_type == voucher_type)
    if cash_account_id:
        stmt = stmt.where(Voucher.cash_account_id == cash_account_id)
    if date_from:
        stmt = stmt.where(Voucher.voucher_date >= date_from)
    if date_to:
        stmt = stmt.where(Voucher.voucher_date <= date_to)
    stmt = stmt.order_by(Voucher.voucher_date.desc(), Voucher.id.desc()).limit(limit)
    return list(session.exec(stmt).all())


def get_voucher(session: Session, vid: int) -> Optional[Voucher]:
    return session.get(Voucher, vid)


def delete_voucher(session: Session, vid: int) -> Tuple[bool, str]:
    """Xóa phiếu thu/chi, hoàn trả số dư quỹ."""
    voucher = session.get(Voucher, vid)
    if not voucher:
        return False, "Phiếu không tồn tại"

    # Kiểm tra kỳ có bị khóa không
    period = voucher.voucher_date.strftime("%Y-%m")
    if is_period_locked(session, period):
        return False, f"Kỳ {period} đã khóa, không thể xóa phiếu"

    acc = session.get(CashAccount, voucher.cash_account_id)
    if acc:
        if voucher.voucher_type == "RECEIPT":
            # Thu → giảm số dư khi xóa
            if acc.current_balance < voucher.amount:
                return False, f"Số dư quỹ không đủ để hoàn tác. Hiện có {acc.current_balance:,.0f}đ"
            acc.current_balance -= voucher.amount
        else:  # PAYMENT
            # Chi → tăng số dư khi xóa
            acc.current_balance += voucher.amount
        session.add(acc)

    session.delete(voucher)
    session.commit()
    return True, "Đã xóa phiếu"


# ============================================================
# AUTO VOUCHER TỪ BÁN HÀNG / MUA HÀNG
# ============================================================
def auto_create_receipt_from_sale(session: Session, sale_order, user_id: Optional[int] = None) -> Optional[Voucher]:
    """Tự động tạo phiếu thu khi đơn bán được thanh toán."""
    # Kiểm tra đã có phiếu thu cho đơn này chưa
    existing = session.exec(
        select(Voucher)
        .where(Voucher.ref_type == "SALE")
        .where(Voucher.ref_id == sale_order.id)
    ).first()
    if existing:
        return existing  # Đã có, không tạo lại

    # Lấy quỹ tiền mặt mặc định
    cash_acc = session.exec(
        select(CashAccount)
        .where(CashAccount.account_type == "CASH")
        .where(CashAccount.status == "ACTIVE")
    ).first()
    if not cash_acc:
        return None

    if sale_order.paid_amount <= 0:
        return None

    from app.modules.ban_hang.models import Customer
    cust = session.get(Customer, sale_order.customer_id) if sale_order.customer_id else None

    data = VoucherCreate(
        voucher_type="RECEIPT",
        cash_account_id=cash_acc.id,
        partner_type="CUSTOMER",
        partner_id=sale_order.customer_id,
        partner_name=cust.name if cust else "Khách lẻ",
        amount=sale_order.paid_amount,
        category="",
        reason=f"Thu tiền đơn bán {sale_order.code}",
        ref_type="SALE",
        ref_id=sale_order.id,
        voucher_date=sale_order.created_at.date(),
    )
    voucher, _ = create_voucher(session, data, user_id)
    return voucher


def auto_create_payment_from_purchase(session: Session, purchase_order, user_id: Optional[int] = None) -> Optional[Voucher]:
    """Tự động tạo phiếu chi khi thanh toán đơn mua."""
    existing = session.exec(
        select(Voucher)
        .where(Voucher.ref_type == "PURCHASE")
        .where(Voucher.ref_id == purchase_order.id)
    ).first()
    if existing:
        return existing

    cash_acc = session.exec(
        select(CashAccount)
        .where(CashAccount.account_type == "CASH")
        .where(CashAccount.status == "ACTIVE")
    ).first()
    if not cash_acc:
        return None

    if purchase_order.paid_amount <= 0:
        return None

    from app.modules.quan_ly_kho.models import Supplier
    sup = session.get(Supplier, purchase_order.supplier_id) if purchase_order.supplier_id else None

    data = VoucherCreate(
        voucher_type="PAYMENT",
        cash_account_id=cash_acc.id,
        partner_type="SUPPLIER",
        partner_id=purchase_order.supplier_id,
        partner_name=sup.name if sup else "",
        amount=purchase_order.paid_amount,
        category="",
        reason=f"Trả tiền đơn mua {purchase_order.code}",
        ref_type="PURCHASE",
        ref_id=purchase_order.id,
        voucher_date=purchase_order.created_at.date(),
    )
    voucher, _ = create_voucher(session, data, user_id)
    return voucher


# ============================================================
# FIXED ASSET (TSCĐ & CCDC)
# ============================================================
def get_all_assets(
    session: Session,
    asset_type: str = "",
    status: str = "",
) -> List[FixedAsset]:
    stmt = select(FixedAsset)
    if asset_type:
        stmt = stmt.where(FixedAsset.asset_type == asset_type)
    if status:
        stmt = stmt.where(FixedAsset.status == status)
    stmt = stmt.order_by(FixedAsset.code)
    return list(session.exec(stmt).all())


def get_asset(session: Session, aid: int) -> Optional[FixedAsset]:
    return session.get(FixedAsset, aid)


def create_asset(session: Session, data: FixedAssetCreate) -> Tuple[Optional[FixedAsset], str]:
    try:
        code = data.code or _gen_code(session, FixedAsset, "TS", length=4)
        asset = FixedAsset(
            code=code,
            name=data.name,
            asset_type=data.asset_type,
            unit=data.unit,
            quantity=data.quantity,
            original_cost=data.original_cost,
            depreciation_rate=data.depreciation_rate,
            purchase_date=data.purchase_date,
            start_use_date=data.start_use_date,
            location=data.location,
            note=data.note,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return asset, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo tài sản: {e}"


def update_asset(session: Session, aid: int, data: FixedAssetUpdate) -> Optional[FixedAsset]:
    asset = session.get(FixedAsset, aid)
    if not asset:
        return None
    for k, v in data.model_dump().items():
        setattr(asset, k, v)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def dispose_asset(session: Session, aid: int, data: AssetDisposal) -> Tuple[bool, str]:
    """Ghi giảm TSCĐ (thanh lý, nhượng bán)."""
    asset = session.get(FixedAsset, aid)
    if not asset:
        return False, "Tài sản không tồn tại"
    if asset.status != "ACTIVE":
        return False, f"Tài sản đã ở trạng thái {asset.status}"

    asset.status = "DISPOSED"
    asset.disposal_date = data.disposal_date
    asset.disposal_reason = data.disposal_reason
    asset.disposal_value = data.disposal_value
    session.add(asset)
    session.commit()
    return True, "Đã ghi giảm tài sản"


def delete_asset(session: Session, aid: int) -> Tuple[bool, str]:
    asset = session.get(FixedAsset, aid)
    if not asset:
        return False, "Tài sản không tồn tại"
    # Kiểm tra có khấu hao chưa
    has_dep = session.exec(
        select(AssetDepreciation).where(AssetDepreciation.asset_id == aid)
    ).first()
    if has_dep:
        return False, "Không thể xóa: Tài sản đã có khấu hao"
    session.delete(asset)
    session.commit()
    return True, "Đã xóa tài sản"


# ============================================================
# KHẤU HAO TÀI SẢN
# ============================================================
def get_asset_depreciations(session: Session, asset_id: int) -> List[AssetDepreciation]:
    return list(session.exec(
        select(AssetDepreciation)
        .where(AssetDepreciation.asset_id == asset_id)
        .order_by(AssetDepreciation.period.desc())
    ).all())


def calc_monthly_depreciation(asset: FixedAsset) -> float:
    """Tính khấu hao 1 tháng = Nguyên giá × Tỷ lệ %/năm / 12."""
    if asset.depreciation_rate <= 0:
        return 0.0
    return asset.original_cost * asset.depreciation_rate / 100 / 12


def run_monthly_depreciation(
    session: Session, period: str, user_id: Optional[int] = None,
) -> Tuple[int, str]:
    """Chạy khấu hao cho tất cả TSCĐ trong 1 tháng."""
    # Kiểm tra kỳ có bị khóa không
    if is_period_locked(session, period):
        return 0, f"Kỳ {period} đã khóa"

    assets = session.exec(
        select(FixedAsset)
        .where(FixedAsset.status == "ACTIVE")
        .where(FixedAsset.asset_type == "TSCD")
        .where(FixedAsset.depreciation_rate > 0)
    ).all()

    count = 0
    total_amount = 0.0

    for asset in assets:
        # Kiểm tra đã chạy cho kỳ này chưa
        existing = session.exec(
            select(AssetDepreciation)
            .where(AssetDepreciation.asset_id == asset.id)
            .where(AssetDepreciation.period == period)
        ).first()
        if existing:
            continue

        monthly = calc_monthly_depreciation(asset)
        if monthly <= 0:
            continue

        # Không vượt quá nguyên giá
        remaining = asset.original_cost - asset.accumulated_depreciation
        if remaining <= 0:
            continue
        actual = min(monthly, remaining)

        dep = AssetDepreciation(
            asset_id=asset.id,
            period=period,
            depreciation_amount=actual,
            accumulated_before=asset.accumulated_depreciation,
            accumulated_after=asset.accumulated_depreciation + actual,
        )
        session.add(dep)

        asset.accumulated_depreciation += actual
        session.add(asset)

        count += 1
        total_amount += actual

    session.commit()
    return count, f"Đã chạy khấu hao {count} tài sản, tổng {total_amount:,.0f}đ"


# ============================================================
# BÁO CÁO SỔ SÁCH THEO TT152
# ============================================================
def report_s1a_s2a_s2b_revenue(
    session: Session, date_from: date, date_to: date,
    business_category: str = "",
) -> List[Dict]:
    """
    Sổ doanh thu bán hàng hóa, dịch vụ (S1a/S2a/S2b-HKD).
    Lấy từ đơn bán hàng đã thanh toán.
    """
    from app.modules.ban_hang.models import SaleOrder, SaleOrderLine
    from app.modules.quan_ly_kho.models import Product

    stmt = (
        select(SaleOrder)
        .where(SaleOrder.created_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
        .where(SaleOrder.created_at <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc))
        .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
    )
    orders = list(session.exec(stmt.order_by(SaleOrder.created_at)).all())

    result = []
    for o in orders:
        lines = session.exec(
            select(SaleOrderLine).where(SaleOrderLine.order_id == o.id)
        ).all()

        # Nhóm theo business_category
        groups: Dict[str, Dict] = {}
        for l in lines:
            p = session.get(Product, l.product_id)
            cat = p.business_category if p else "RETAIL"
            if business_category and cat != business_category:
                continue
            if cat not in groups:
                groups[cat] = {"amount": 0.0, "qty": 0}
            groups[cat]["amount"] += l.line_total
            groups[cat]["qty"] += l.base_quantity

        for cat, g in groups.items():
            result.append({
                "date": o.created_at.date(),
                "code": o.code,
                "diary": f"Bán hàng đơn {o.code}",
                "business_category": cat,
                "quantity": g["qty"],
                "amount": g["amount"],
                "note": o.note,
            })

    return result


def report_s2c_revenue_expense(
    session: Session, date_from: date, date_to: date,
) -> List[Dict]:
    """
    Sổ chi tiết doanh thu - chi phí (S2c-HKD).
    Gồm: doanh thu từ bán hàng + chi phí từ phiếu chi + giá vốn hàng bán.
    """
    result = []

    # 1. Doanh thu
    dt = report_s1a_s2a_s2b_revenue(session, date_from, date_to)
    for r in dt:
        result.append({
            "date": r["date"],
            "diary": r["diary"],
            "revenue": r["amount"],
            "expense": 0.0,
            "category": "Doanh thu bán hàng",
        })

    # 2. Chi phí từ phiếu chi
    vouchers = get_all_vouchers(
        session, voucher_type="PAYMENT",
        date_from=date_from, date_to=date_to,
    )
    for v in vouchers:
        result.append({
            "date": v.voucher_date,
            "diary": v.reason,
            "revenue": 0.0,
            "expense": v.amount,
            "category": v.category or "Chi phí khác",
        })

    # Sort theo ngày
    result.sort(key=lambda x: x["date"])
    return result


def report_s2e_cash_detail(
    session: Session, cash_account_id: int,
    date_from: date, date_to: date,
) -> Dict:
    """
    Sổ chi tiết tiền (S2e-HKD).
    Trả về: opening, list giao dịch, closing.
    """
    acc = session.get(CashAccount, cash_account_id)
    if not acc:
        return {"opening": 0, "transactions": [], "closing": 0}

    # Số dư đầu kỳ = opening_balance + tổng thu/chi TRƯỚC date_from
    before_receipts = session.exec(
        select(func.coalesce(func.sum(Voucher.amount), 0))
        .where(Voucher.cash_account_id == cash_account_id)
        .where(Voucher.voucher_type == "RECEIPT")
        .where(Voucher.voucher_date < date_from)
    ).one() or 0
    before_payments = session.exec(
        select(func.coalesce(func.sum(Voucher.amount), 0))
        .where(Voucher.cash_account_id == cash_account_id)
        .where(Voucher.voucher_type == "PAYMENT")
        .where(Voucher.voucher_date < date_from)
    ).one() or 0

    opening = acc.opening_balance + before_receipts - before_payments

    # Giao dịch trong kỳ
    vouchers = get_all_vouchers(
        session,
        cash_account_id=cash_account_id,
        date_from=date_from, date_to=date_to,
    )
    vouchers_asc = sorted(vouchers, key=lambda v: (v.voucher_date, v.id))

    transactions = []
    running = opening
    for v in vouchers_asc:
        if v.voucher_type == "RECEIPT":
            running += v.amount
        else:
            running -= v.amount
        transactions.append({
            "date": v.voucher_date,
            "code": v.code,
            "diary": v.reason,
            "receipt": v.amount if v.voucher_type == "RECEIPT" else 0,
            "payment": v.amount if v.voucher_type == "PAYMENT" else 0,
            "balance": running,
        })

    return {
        "account": acc,
        "opening": opening,
        "transactions": transactions,
        "closing": running,
    }


def report_tax_summary(
    session: Session, date_from: date, date_to: date,
) -> Dict:
    """Tổng hợp thuế GTGT và TNCN phải nộp (HKD)."""
    profile = get_hkd_profile(session)
    if not profile:
        return {"vat": 0, "tncn": 0, "revenue": 0, "total": 0}

    # Tổng doanh thu
    dt = report_s1a_s2a_s2b_revenue(session, date_from, date_to)
    total_revenue = sum(r["amount"] for r in dt)

    vat = 0.0
    tncn = 0.0

    if profile.hkd_group == 1:
        # Nhóm 1: miễn thuế
        pass
    elif profile.hkd_group == 2:
        # Nhóm 2: GTGT + TNCN theo % doanh thu
        vat = total_revenue * profile.vat_rate_retail / 100
        tncn = total_revenue * profile.tncn_rate / 100
    elif profile.hkd_group == 3:
        # Nhóm 3: GTGT theo % DT + TNCN trên thu nhập
        vat = total_revenue * profile.vat_rate_retail / 100
        # Thu nhập = DT - Chi phí
        expenses = session.exec(
            select(func.coalesce(func.sum(Voucher.amount), 0))
            .where(Voucher.voucher_type == "PAYMENT")
            .where(Voucher.voucher_date >= date_from)
            .where(Voucher.voucher_date <= date_to)
        ).one() or 0
        income = max(0, total_revenue - expenses)
        tncn = income * profile.tncn_rate / 100

    return {
        "revenue": total_revenue,
        "vat": vat,
        "tncn": tncn,
        "total": vat + tncn,
        "hkd_group": profile.hkd_group,
    }


def report_debt_summary(session: Session) -> Dict:
    """Báo cáo công nợ tổng hợp (KH + NCC)."""
    from app.modules.ban_hang.models import Customer
    from app.modules.quan_ly_kho.models import Supplier

    # Công nợ phải thu KH
    customers = session.exec(
        select(Customer).where(Customer.current_debt > 0).order_by(Customer.current_debt.desc())
    ).all()
    receivable = sum(c.current_debt for c in customers)

    # Công nợ phải trả NCC
    suppliers = session.exec(
        select(Supplier).where(Supplier.current_debt > 0).order_by(Supplier.current_debt.desc())
    ).all()
    payable = sum(s.current_debt for s in suppliers)

    return {
        "customers": customers,
        "suppliers": suppliers,
        "receivable": receivable,
        "payable": payable,
        "net": receivable - payable,
    }

def delete_asset_depreciations(session: Session, asset_id: int) -> Tuple[bool, str]:
    """Xóa toàn bộ khấu hao của 1 tài sản và reset accumulated = 0."""
    deps = session.exec(
        select(AssetDepreciation).where(AssetDepreciation.asset_id == asset_id)
    ).all()
    if not deps:
        return False, "Tài sản chưa có khấu hao"

    for d in deps:
        session.delete(d)

    # Reset accumulated
    asset = session.get(FixedAsset, asset_id)
    if asset:
        asset.accumulated_depreciation = 0
        session.add(asset)

    session.commit()
    return True, f"Đã xóa {len(deps)} bản ghi khấu hao. Giá trị còn lại được khôi phục."


def delete_depreciation_by_period(session: Session, period: str) -> Tuple[bool, str]:
    """Xóa toàn bộ khấu hao của 1 kỳ (tất cả tài sản)."""
    deps = session.exec(
        select(AssetDepreciation).where(AssetDepreciation.period == period)
    ).all()
    if not deps:
        return False, f"Không có khấu hao nào cho kỳ {period}"

    for d in deps:
        # Trừ ngược accumulated của tài sản
        asset = session.get(FixedAsset, d.asset_id)
        if asset:
            asset.accumulated_depreciation -= d.depreciation_amount
            if asset.accumulated_depreciation < 0:
                asset.accumulated_depreciation = 0
            session.add(asset)
        session.delete(d)

    session.commit()
    return True, f"Đã xóa {len(deps)} bản ghi khấu hao kỳ {period}"