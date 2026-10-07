# app/modules/ban_hang/services.py
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from sqlmodel import Session, select, func, or_

from app.modules.ban_hang.models import (
    Customer, SaleDiscountCode, SaleShift, SaleShiftDenomination,
    SaleOrder, SaleOrderLine, SalePayment, SaleReturn, SaleReturnLine,
    VatCustomer,
)
from app.modules.ban_hang.schemas import (
    CustomerCreate, CustomerUpdate,
    DiscountCodeCreate, DiscountCodeUpdate,
    ShiftOpen, ShiftClose,
    SaleOrderCreate, SaleOrderLineCreate,
    PaymentCreate, ReturnCreate,
)
from app.modules.quan_ly_kho.models import Product, ProductUoM, StockMove
from app.modules.quan_ly_kho import services as kho_services
from app.modules.quan_ly_kho.schemas import StockMoveCreateFull

# ============================================================
# HELPER: Lazy import kế toán để tránh circular import
# ============================================================
def _get_default_cash_account(session: Session):
    """Lấy tài khoản quỹ tiền mặt mặc định."""
    from app.modules.ke_toan.models import CashAccount
    return session.exec(
        select(CashAccount)
        .where(CashAccount.account_type == "CASH")
        .where(CashAccount.status == "ACTIVE")
    ).first()


def _get_default_bank_account(session: Session):
    """Lấy tài khoản ngân hàng mặc định."""
    from app.modules.ke_toan.models import CashAccount
    return session.exec(
        select(CashAccount)
        .where(CashAccount.account_type == "BANK")
        .where(CashAccount.status == "ACTIVE")
    ).first()


def _create_receipt_voucher(
    session: Session, cash_account_id: int, amount: float,
    reason: str, category: str = "DOANHTHU",
    ref_type: str = "SHIFT", ref_id: Optional[int] = None,
    partner_name: str = "", voucher_date=None,
) -> Optional[int]:
    """Sinh phiếu thu kế toán. Trả về voucher.id hoặc None nếu lỗi."""
    try:
        from app.modules.ke_toan.services import create_voucher
        from app.modules.ke_toan.schemas import VoucherCreate

        data = VoucherCreate(
            voucher_type="RECEIPT",
            cash_account_id=cash_account_id,
            partner_type="OTHER",
            partner_name=partner_name,
            amount=amount,
            category=category,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            voucher_date=voucher_date,
        )
        voucher, msg = create_voucher(session, data)
        if voucher:
            return voucher.id
        print(f"[WARN] Không sinh được phiếu thu: {msg}")
        return None
    except Exception as e:
        print(f"[ERROR] Lỗi sinh phiếu thu: {e}")
        return None


def _create_payment_voucher(
    session: Session, cash_account_id: int, amount: float,
    reason: str, category: str = "CHIPHIKHAC",
    ref_type: str = "SHIFT", ref_id: Optional[int] = None,
    partner_name: str = "", voucher_date=None,
) -> Optional[int]:
    """Sinh phiếu chi kế toán. Trả về voucher.id hoặc None nếu lỗi."""
    try:
        from app.modules.ke_toan.services import create_voucher
        from app.modules.ke_toan.schemas import VoucherCreate

        data = VoucherCreate(
            voucher_type="PAYMENT",
            cash_account_id=cash_account_id,
            partner_type="OTHER",
            partner_name=partner_name,
            amount=amount,
            category=category,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            voucher_date=voucher_date,
        )
        voucher, msg = create_voucher(session, data)
        if voucher:
            return voucher.id
        print(f"[WARN] Không sinh được phiếu chi: {msg}")
        return None
    except Exception as e:
        print(f"[ERROR] Lỗi sinh phiếu chi: {e}")
        return None


# ============================================================
# HELPERS
# ============================================================
def _gen_code(session: Session, model, prefix: str) -> str:
    """Sinh mã tự động: PREFIX + số thứ tự."""
    today = datetime.now().strftime("%y%m%d")
    pattern = f"{prefix}{today}%"
    stmt = select(func.count()).select_from(model).where(model.code.like(pattern))
    count = session.exec(stmt).one() or 0
    return f"{prefix}{today}{count + 1:04d}"

def _find_last_cost_price(
    session: Session, product_id: int, customer_type: str = "RETAIL"
) -> float:
    """
    Tìm giá vốn gần nhất của sản phẩm theo loại khách hàng.
    - Nếu cùng loại khách (RETAIL/WHOLESALE) → ưu tiên.
    - Nếu không có → tìm bất kỳ loại khách nào.
    """
    # Ưu tiên 1: Cùng loại khách
    stmt = (
        select(SaleOrderLine.cost_price_at_sale)
        .join(SaleOrder, SaleOrderLine.order_id == SaleOrder.id)
        .join(Customer, SaleOrder.customer_id == Customer.id)
        .where(SaleOrderLine.product_id == product_id)
        .where(SaleOrderLine.cost_price_at_sale > 0)
        .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
        .where(Customer.customer_type == customer_type)
        .order_by(SaleOrder.created_at.desc())
        .limit(1)
    )
    cost = session.exec(stmt).first()
    if cost and cost > 0:
        return cost

    # Ưu tiên 2: Bất kỳ loại khách nào
    stmt = (
        select(SaleOrderLine.cost_price_at_sale)
        .join(SaleOrder, SaleOrderLine.order_id == SaleOrder.id)
        .where(SaleOrderLine.product_id == product_id)
        .where(SaleOrderLine.cost_price_at_sale > 0)
        .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
        .order_by(SaleOrder.created_at.desc())
        .limit(1)
    )
    cost = session.exec(stmt).first()
    return cost if cost and cost > 0 else 0.0


# ============================================================
# CUSTOMER
# ============================================================
def get_all_customers(session: Session, keyword: str = "") -> List[Customer]:
    stmt = select(Customer)
    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(or_(
            Customer.code.like(p), Customer.name.like(p),
            Customer.phone.like(p),
        ))
    return list(session.exec(stmt.order_by(Customer.name)).all())


def get_customer(session: Session, cid: int) -> Optional[Customer]:
    return session.get(Customer, cid)


def get_customer_by_phone(session: Session, phone: str) -> Optional[Customer]:
    if not phone:
        return None
    return session.exec(select(Customer).where(Customer.phone == phone)).first()


def get_default_customer(session: Session) -> Customer:
    """Lấy khách hàng mặc định 'Bán cho người tiêu dùng'."""
    c = session.exec(
        select(Customer).where(Customer.code == "KHL")
    ).first()
    if not c:
        c = Customer(
            code="KHL",
            name="Bán cho người tiêu dùng",
            customer_type="RETAIL",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
    return c


def create_customer(session: Session, data: CustomerCreate) -> Customer:
    c = Customer(**data.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def update_customer(session: Session, cid: int, data: CustomerUpdate) -> Optional[Customer]:
    c = session.get(Customer, cid)
    if not c:
        return None
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def delete_customer(session: Session, cid: int) -> Tuple[bool, str]:
    c = session.get(Customer, cid)
    if not c:
        return False, "Khách hàng không tồn tại"
    if c.code == "KHL":
        return False, "Không thể xóa khách hàng mặc định"
    used = session.exec(select(SaleOrder).where(SaleOrder.customer_id == cid)).first()
    if used:
        return False, "Không thể xóa: Khách đã có đơn hàng"
    if c.current_debt != 0:
        return False, f"Không thể xóa: Khách còn nợ {c.current_debt:,.0f}đ"
    session.delete(c)
    session.commit()
    return True, "Đã xóa khách hàng"


# ============================================================
# DISCOUNT CODE
# ============================================================
def get_all_discount_codes(session: Session, only_active: bool = False) -> List[SaleDiscountCode]:
    stmt = select(SaleDiscountCode)
    if only_active:
        stmt = stmt.where(SaleDiscountCode.status == "ACTIVE")
    return list(session.exec(stmt.order_by(SaleDiscountCode.code)).all())


def get_discount_code(session: Session, did: int) -> Optional[SaleDiscountCode]:
    return session.get(SaleDiscountCode, did)


def get_discount_by_code(session: Session, code: str) -> Optional[SaleDiscountCode]:
    return session.exec(
        select(SaleDiscountCode).where(SaleDiscountCode.code == code)
    ).first()


def create_discount_code(session: Session, data: DiscountCodeCreate) -> SaleDiscountCode:
    d = SaleDiscountCode(**data.model_dump())
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def update_discount_code(session: Session, did: int, data: DiscountCodeUpdate) -> Optional[SaleDiscountCode]:
    d = session.get(SaleDiscountCode, did)
    if not d:
        return None
    for k, v in data.model_dump().items():
        setattr(d, k, v)
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def delete_discount_code(session: Session, did: int) -> Tuple[bool, str]:
    d = session.get(SaleDiscountCode, did)
    if not d:
        return False, "Mã không tồn tại"
    if d.used_count > 0:
        return False, "Không thể xóa: Mã đã được sử dụng"
    session.delete(d)
    session.commit()
    return True, "Đã xóa mã giảm giá"


def validate_discount_code(session: Session, code: str, order_amount: float) -> Tuple[Optional[SaleDiscountCode], str]:
    """Kiểm tra mã giảm giá có hợp lệ không."""
    d = get_discount_by_code(session, code)
    if not d:
        return None, "Mã giảm giá không tồn tại"
    if d.status != "ACTIVE":
        return None, "Mã giảm giá đã ngừng hoạt động"
    now = datetime.now(timezone.utc)
    if d.valid_from and d.valid_from > now:
        return None, "Mã chưa đến thời gian sử dụng"
    if d.valid_to and d.valid_to < now:
        return None, "Mã đã hết hạn"
    if d.max_uses > 0 and d.used_count >= d.max_uses:
        return None, "Mã đã hết lượt sử dụng"
    if order_amount < d.min_order_amount:
        return None, f"Đơn hàng tối thiểu {d.min_order_amount:,.0f}đ để dùng mã"
    return d, "OK"


def calc_discount_amount(d: SaleDiscountCode, order_amount: float) -> float:
    if d.discount_type == "PERCENT":
        amount = order_amount * d.discount_value / 100
        if d.max_discount > 0:
            amount = min(amount, d.max_discount)
        return amount
    else:  # AMOUNT
        return min(d.discount_value, order_amount)


# ============================================================
# SHIFT (CA LÀM VIỆC)
# ============================================================
def get_open_shift(session: Session, user_id: Optional[int] = None) -> Optional[SaleShift]:
    stmt = select(SaleShift).where(SaleShift.status == "OPEN")
    if user_id is not None:
        stmt = stmt.where(SaleShift.user_id == user_id)
    return session.exec(stmt.order_by(SaleShift.opened_at.desc())).first()


def open_shift(session: Session, data: ShiftOpen) -> SaleShift:
    s = SaleShift(
        code=_gen_code(session, SaleShift, "CA"),
        opening_cash=data.opening_cash,
        user_id=data.user_id,
        note=data.note,
        status="OPEN",
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def get_shift(session: Session, sid: int) -> Optional[SaleShift]:
    return session.get(SaleShift, sid)


def preview_close_shift(session: Session, sid: int) -> dict:
    """
    Xem trước số liệu khi đóng ca (chưa commit).
    Trả về dict cho UI hiển thị cảnh báo.
    """
    from app.modules.ke_toan.models import HKDProfile

    s = session.get(SaleShift, sid)
    if not s:
        return {"ok": False, "message": "Ca không tồn tại"}
    if s.status == "CLOSED":
        return {"ok": False, "message": "Ca đã đóng"}

    # Lấy toàn bộ đơn hàng trong ca
    orders = session.exec(
        select(SaleOrder).where(SaleOrder.shift_id == sid)
    ).all()

    total_revenue = sum(o.total_amount for o in orders if o.status != "CANCELLED")

    # Tổng hợp theo phương thức
    payments = session.exec(
        select(SalePayment)
        .join(SaleOrder, SalePayment.order_id == SaleOrder.id)
        .where(SaleOrder.shift_id == sid)
    ).all()

    total_cash = 0.0
    total_bank = 0.0
    total_card = 0.0
    total_debt = 0.0
    for p in payments:
        if p.payment_method == "CASH":
            total_cash += p.amount
        elif p.payment_method == "BANK":
            total_bank += p.amount
        elif p.payment_method == "CARD":
            total_card += p.amount
        elif p.payment_method == "DEBT":
            total_debt += p.amount

    # Trả hàng
    returns = session.exec(
        select(SaleReturn).where(SaleReturn.shift_id == sid)
    ).all()
    total_returns = sum(r.total_amount for r in returns if r.status == "CONFIRMED")

    # Tính
    net_cash = total_cash - total_returns
    expected_cash = s.opening_cash + net_cash
    change = s.counted_cash - expected_cash

    # Ngưỡng cảnh báo
    profile = session.exec(select(HKDProfile)).first()
    threshold = profile.shift_diff_threshold if profile else 50000.0

    # Danh sách phiếu sẽ sinh
    planned_vouchers = []
    if net_cash > 0:
        planned_vouchers.append({
            "type": "receipt",
            "label": "Doanh thu tiền mặt",
            "amount": net_cash,
            "account_type": "cash",
        })
    if total_bank > 0:
        planned_vouchers.append({
            "type": "receipt",
            "label": "Doanh thu chuyển khoản",
            "amount": total_bank,
            "account_type": "bank",
        })
    if change > 0:
        planned_vouchers.append({
            "type": "receipt",
            "label": f"Thu nhập khác (chênh lệch +)",
            "amount": change,
            "account_type": "cash",
        })
    elif change < 0:
        planned_vouchers.append({
            "type": "payment",
            "label": f"Chi phí khác (chênh lệch -)",
            "amount": abs(change),
            "account_type": "cash",
        })

    # Cảnh báo nếu chênh lệch lớn
    warning = None
    if abs(change) > threshold:
        warning = (
            f"⚠️ CHÊNH LỆCH LỚN: {change:,.0f}đ (vượt ngưỡng {threshold:,.0f}đ)\n\n"
            f"Vui lòng kiểm tra lại:\n"
            f"  • Tiền lẻ đầu ca:       {s.opening_cash:,.0f}đ\n"
            f"  • Tiền mặt bán trong ca: {total_cash:,.0f}đ\n"
            f"  • Tiền CK bán trong ca:  {total_bank:,.0f}đ\n"
            f"  • Tiền thẻ bán trong ca: {total_card:,.0f}đ\n"
            f"  • Tiền mặt trả hàng:     {total_returns:,.0f}đ\n"
            f"  • Tiền mặt đếm thực tế:  {s.counted_cash:,.0f}đ"
        )

    return {
        "ok": True,
        "shift_id": s.id,
        "shift_code": s.code,
        "opening_cash": s.opening_cash,
        "total_cash": total_cash,
        "total_bank": total_bank,
        "total_card": total_card,
        "total_debt": total_debt,
        "total_returns": total_returns,
        "net_cash": net_cash,
        "total_revenue": total_revenue,
        "expected_cash": expected_cash,
        "counted_cash": s.counted_cash,
        "change": change,
        "threshold": threshold,
        "warning": warning,
        "planned_vouchers": planned_vouchers,
    }


def close_shift(
    session: Session, sid: int, data: "ShiftClose",
) -> Tuple[bool, str, Optional[SaleShift]]:
    """
    Đóng ca: tính tổng doanh thu, kiểm đếm mệnh giá, sinh phiếu thu/chi tự động.
    """
    s = session.get(SaleShift, sid)
    if not s:
        return False, "Ca không tồn tại", None
    if s.status == "CLOSED":
        return False, "Ca đã đóng", None

    # Lấy toàn bộ đơn hàng trong ca
    orders = session.exec(
        select(SaleOrder).where(SaleOrder.shift_id == sid)
    ).all()
    total_revenue = sum(o.total_amount for o in orders if o.status != "CANCELLED")

    # Tổng hợp payments
    payments = session.exec(
        select(SalePayment)
        .join(SaleOrder, SalePayment.order_id == SaleOrder.id)
        .where(SaleOrder.shift_id == sid)
    ).all()

    total_cash = 0.0
    total_bank = 0.0
    total_card = 0.0
    total_debt = 0.0
    for p in payments:
        if p.payment_method == "CASH":
            total_cash += p.amount
        elif p.payment_method == "BANK":
            total_bank += p.amount
        elif p.payment_method == "CARD":
            total_card += p.amount
        elif p.payment_method == "DEBT":
            total_debt += p.amount

    # Trả hàng
    returns = session.exec(
        select(SaleReturn).where(SaleReturn.shift_id == sid)
    ).all()
    total_returns = sum(r.total_amount for r in returns if r.status == "CONFIRMED")

    net_cash = total_cash - total_returns
    expected_cash = s.opening_cash + net_cash
    change = data.counted_cash - expected_cash

    # Xác định tài khoản nhận
    cash_acc_id = data.cash_account_id
    bank_acc_id = data.bank_account_id

    if not cash_acc_id:
        acc = _get_default_cash_account(session)
        cash_acc_id = acc.id if acc else None

    if not bank_acc_id and total_bank > 0:
        acc = _get_default_bank_account(session)
        bank_acc_id = acc.id if acc else None

    # === SINH PHIẾU THU/CHI TỰ ĐỘNG ===
    voucher_ids = []

    # 1. Phiếu thu tiền mặt (net)
    if net_cash > 0 and cash_acc_id:
        vid = _create_receipt_voucher(
            session, cash_acc_id, net_cash,
            reason=f"Doanh thu tiền mặt ca {s.code}",
            category="DOANHTHU",
            ref_type="SHIFT", ref_id=s.id,
            voucher_date=s.closed_at or datetime.now(timezone.utc).date() if False else None,
        )
        if vid:
            voucher_ids.append(vid)

    # 2. Phiếu thu CK
    if total_bank > 0 and bank_acc_id:
        vid = _create_receipt_voucher(
            session, bank_acc_id, total_bank,
            reason=f"Doanh thu chuyển khoản ca {s.code}",
            category="DOANHTHU",
            ref_type="SHIFT", ref_id=s.id,
        )
        if vid:
            voucher_ids.append(vid)

    # 3. Chênh lệch
    if change > 0 and cash_acc_id:
        vid = _create_receipt_voucher(
            session, cash_acc_id, change,
            reason=f"Thu nhập khác - chênh lệch tiền mặt ca {s.code}",
            category="THUNHAPKHAC",
            ref_type="SHIFT", ref_id=s.id,
        )
        if vid:
            voucher_ids.append(vid)
    elif change < 0 and cash_acc_id:
        vid = _create_payment_voucher(
            session, cash_acc_id, abs(change),
            reason=f"Chi phí khác - chênh lệch tiền mặt ca {s.code}",
            category="CHIPHIKHAC",
            ref_type="SHIFT", ref_id=s.id,
        )
        if vid:
            voucher_ids.append(vid)

    # Lưu mệnh giá
    for den in data.denominations:
        d = SaleShiftDenomination(
            shift_id=sid,
            denomination=den.denomination,
            quantity=den.quantity,
            subtotal=den.denomination * den.quantity,
        )
        session.add(d)

    # Cập nhật shift
    s.total_cash_sales = total_cash
    s.total_bank_sales = total_bank
    s.total_card_sales = total_card
    s.total_debt_sales = total_debt
    s.total_returns = total_returns
    s.total_revenue = total_revenue
    s.counted_cash = data.counted_cash
    s.cash_difference = change
    s.cash_account_id = cash_acc_id
    s.bank_account_id = bank_acc_id
    s.shift_receipt_ids = ",".join(str(x) for x in voucher_ids)
    s.closed_at = datetime.now(timezone.utc)
    s.status = "CLOSED"
    if data.note:
        s.note = (s.note + "\n" + data.note).strip()

    session.add(s)
    session.commit()
    session.refresh(s)

    msg = f"Đã đóng ca. Chênh lệch: {change:,.0f}đ"
    if voucher_ids:
        msg += f" — Đã sinh {len(voucher_ids)} phiếu kế toán"
    return True, msg, s

def get_all_shifts(session: Session) -> List[SaleShift]:
    return list(session.exec(
        select(SaleShift).order_by(SaleShift.opened_at.desc())
    ).all())


def get_shift_denominations(session: Session, sid: int) -> List[SaleShiftDenomination]:
    return list(session.exec(
        select(SaleShiftDenomination).where(SaleShiftDenomination.shift_id == sid)
    ).all())


# ============================================================
# SALE ORDER — TÍNH TOÁN
# ============================================================
def _calc_order_totals(lines_data: List[SaleOrderLineCreate], discount_amount: float):
    """Tính tổng tiền đơn hàng từ danh sách dòng."""
    lines = []
    subtotal = 0.0
    total_tax = 0.0

    for l in lines_data:
        # Tính base_quantity (nếu có UoM)
        base_qty = l.quantity
        if l.uom_id:
            # Sẽ tra ở hàm gọi (cần session), tạm để ở đây
            pass

        line_amount = l.quantity * l.unit_price
        line_discount = line_amount * l.discount_percent / 100
        line_after_discount = line_amount - line_discount
        line_tax = line_after_discount * l.tax_rate / 100

        subtotal += line_after_discount
        total_tax += line_tax

        lines.append({
            "product_id": l.product_id,
            "uom_id": l.uom_id,
            "quantity": l.quantity,
            "base_quantity": base_qty,
            "unit_price": l.unit_price,
            "discount_percent": l.discount_percent,
            "discount_amount": line_discount,
            "tax_rate": l.tax_rate,
            "line_subtotal": line_amount,
            "line_tax": line_tax,
            "line_total": line_after_discount + line_tax,
        })

    total_amount = subtotal + total_tax - discount_amount
    if total_amount < 0:
        total_amount = 0

    return {
        "lines": lines,
        "subtotal": subtotal,
        "tax_amount": total_tax,
        "discount_amount": discount_amount,
        "total_amount": total_amount,
    }


def create_sale_order(
    session: Session, data: SaleOrderCreate,
    user_id: Optional[int] = None,
    auto_confirm: bool = True,
) -> Tuple[Optional[SaleOrder], str]:
    """Tạo đơn hàng POS/INVOICE. Nếu auto_confirm=True → xuất kho luôn."""
    try:
        # Xử lý mã giảm giá
        discount_amount = data.discount_amount
        discount_code_id = data.discount_code_id

        if discount_code_id:
            d = session.get(SaleDiscountCode, discount_code_id)
            if d:
                # Tính tạm subtotal để check min_order
                temp_subtotal = sum(l.quantity * l.unit_price for l in data.lines)
                ok_d, msg = validate_discount_code(session, d.code, temp_subtotal)
                if ok_d:
                    # Nếu chưa nhập discount_amount thì tự tính
                    if discount_amount == 0:
                        discount_amount = calc_discount_amount(d, temp_subtotal)

        # Tính toán
        totals = _calc_order_totals(data.lines, discount_amount)

        # Lấy ca đang mở
        shift = get_open_shift(session, user_id)

        # Sinh mã đơn
        prefix = "POS" if data.order_type == "POS" else "HD"
        code = _gen_code(session, SaleOrder, prefix)

        # Xác định customer
        customer_id = data.customer_id
        if not customer_id:
            default_cust = get_default_customer(session)
            customer_id = default_cust.id

        # Tạo đơn
        order = SaleOrder(
            code=code,
            customer_id=customer_id,
            shift_id=shift.id if shift else None,
            discount_code_id=discount_code_id,
            user_id=user_id,
            order_type=data.order_type,
            status="DRAFT",
            subtotal=totals["subtotal"],
            discount_amount=totals["discount_amount"],
            tax_amount=totals["tax_amount"],
            total_amount=totals["total_amount"],
            payment_method=data.payment_method,
            want_vat_invoice=data.want_vat_invoice,
            vat_company_name=data.vat_company_name,
            vat_tax_code=data.vat_tax_code,
            vat_address=data.vat_address,
            vat_email=data.vat_email,
            customer_phone=data.customer_phone,
            customer_paid=data.customer_paid,
            note=data.note,
        )
        session.add(order)
        session.flush()  # Lấy ID

        # Tạo các dòng + xuất kho nếu auto_confirm
        for ldata in totals["lines"]:
            # Nếu có UoM, quy đổi
            base_qty = ldata["quantity"]
            if ldata["uom_id"]:
                uom = session.get(ProductUoM, ldata["uom_id"])
                if uom:
                    base_qty = ldata["quantity"] * uom.factor

            line = SaleOrderLine(
                order_id=order.id,
                product_id=ldata["product_id"],
                uom_id=ldata["uom_id"],
                quantity=ldata["quantity"],
                base_quantity=base_qty,
                unit_price=ldata["unit_price"],
                discount_percent=ldata["discount_percent"],
                discount_amount=ldata["discount_amount"],
                tax_rate=ldata["tax_rate"],
                line_subtotal=ldata["line_subtotal"],
                line_tax=ldata["line_tax"],
                line_total=ldata["line_total"],
            )

            # Xuất kho luôn nếu auto_confirm
            if auto_confirm:
                try:
                    move = kho_services.create_stock_move(session, StockMoveCreateFull(
                        product_id=ldata["product_id"],
                        quantity=base_qty,
                        unit_price=ldata["unit_price"],
                        move_type="OUT",
                        uom_id=ldata["uom_id"],
                        uom_quantity=ldata["quantity"],
                        export_reason="BÁN",
                        note=f"Bán theo đơn {code}",
                    ))
                    line.stock_move_id = move.id
                    line.cost_price_at_sale = move.cost_price_at_move
                except ValueError as e:
                    session.rollback()
                    return None, f"Lỗi xuất kho: {e}"

            session.add(line)

               # === XỬ LÝ THANH TOÁN + CÔNG NỢ ===
        if data.paid_amount > 0:
            # Có thanh toán → tạo payment record
            payment = SalePayment(
                order_id=order.id,
                amount=data.paid_amount,
                payment_method=data.payment_method,
            )
            session.add(payment)
            order.paid_amount = data.paid_amount

            # Set trạng thái
            if data.paid_amount >= order.total_amount - 0.01:
                order.status = "PAID"
                order.paid_amount = order.total_amount
            else:
                order.status = "PARTIAL"

            # Chỉ tăng công nợ khi có phần chưa trả
            remaining = order.total_amount - data.paid_amount
            if remaining > 0.01 and customer_id:
                cust = session.get(Customer, customer_id)
                if cust:
                    cust.current_debt += remaining
                    session.add(cust)

        elif auto_confirm:
            # Không thanh toán gì → ghi nợ toàn bộ
            if customer_id:
                cust = session.get(Customer, customer_id)
                if cust:
                    cust.current_debt += order.total_amount
                    session.add(cust)
            order.status = "CONFIRMED"

        # Tính tiền thối nếu trả tiền mặt (độc lập, không elif)
        if data.payment_method == "CASH" and data.customer_paid > 0:
            order.customer_paid = data.customer_paid
            change = data.customer_paid - order.total_amount
            order.change_amount = change if change > 0 else 0

        # Tăng used_count cho mã giảm giá
        if discount_code_id:
            d = session.get(SaleDiscountCode, discount_code_id)
            if d:
                d.used_count += 1
                session.add(d)

        # Cộng điểm loyalty
        if customer_id:
            cust = session.get(Customer, customer_id)
            if cust:
                points = int(order.total_amount / 10000)  # 10,000đ = 1 điểm
                cust.loyalty_points += points
                session.add(cust)

        # Lưu thông tin KH VAT (nếu có xuất hóa đơn)
        if data.want_vat_invoice and data.vat_tax_code and data.vat_company_name:
            upsert_vat_customer(
                session,
                tax_code=data.vat_tax_code,
                company_name=data.vat_company_name,
                address=data.vat_address,
                email=data.vat_email,
                phone=data.customer_phone,
                customer_id=customer_id if customer_id else None,
            )

        session.add(order)
        session.commit()
        session.refresh(order)
        return order, "OK"

    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo đơn: {e}"


# ============================================================
# SALE ORDER — QUERY
# ============================================================
def get_order(session: Session, oid: int) -> Optional[SaleOrder]:
    return session.get(SaleOrder, oid)


def get_order_lines(session: Session, oid: int) -> List[SaleOrderLine]:
    return list(session.exec(
        select(SaleOrderLine).where(SaleOrderLine.order_id == oid)
    ).all())


def get_order_payments(session: Session, oid: int) -> List[SalePayment]:
    return list(session.exec(
        select(SalePayment).where(SalePayment.order_id == oid)
    ).all())


def get_all_orders(
    session: Session,
    keyword: str = "",
    status: str = "",
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 100,
) -> List[SaleOrder]:
    stmt = select(SaleOrder)
    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(SaleOrder.code.like(p))
    if status:
        stmt = stmt.where(SaleOrder.status == status)
    if date_from:
        stmt = stmt.where(SaleOrder.created_at >= date_from)
    if date_to:
        stmt = stmt.where(SaleOrder.created_at <= date_to)
    stmt = stmt.order_by(SaleOrder.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


# ============================================================
# THANH TOÁN
# ============================================================
def add_payment(session: Session, data: PaymentCreate) -> Tuple[bool, str]:
    try:
        order = session.get(SaleOrder, data.order_id)
        if not order:
            return False, "Đơn hàng không tồn tại"
        if order.status == "CANCELLED":
            return False, "Đơn hàng đã hủy"
        if order.status == "PAID":
            return False, "Đơn hàng đã thanh toán đủ"

        remaining = order.total_amount - order.paid_amount
        if data.amount > remaining + 0.01:
            return False, f"Số tiền vượt quá số còn lại ({remaining:,.0f}đ)"

        payment = SalePayment(
            order_id=order.id,
            amount=data.amount,
            payment_method=data.payment_method,
            cash_account_id=data.cash_account_id,
            bank_transaction_code=data.bank_transaction_code,
            note=data.note,
        )
        session.add(payment)

        order.paid_amount += data.amount
        if order.paid_amount >= order.total_amount - 0.01:
            order.status = "PAID"
            order.paid_amount = order.total_amount
        else:
            order.status = "PARTIAL"

        # Giảm công nợ KH
        if order.customer_id:
            cust = session.get(Customer, order.customer_id)
            if cust:
                cust.current_debt -= data.amount
                if cust.current_debt < 0:
                    cust.current_debt = 0
                session.add(cust)

        session.add(order)

        # Sinh phiếu thu nếu có chọn tài khoản quỹ
        if data.cash_account_id:
            _create_receipt_voucher(
                session, data.cash_account_id, data.amount,
                reason=f"Thu tiền đơn {order.code}" + (f" - {data.note}" if data.note else ""),
                category="DOANHTHU",
                ref_type="SALE", ref_id=order.id,
                partner_name=cust_name if (cust := session.get(Customer, order.customer_id)) else "",
            )

        session.commit()
        return True, "Đã ghi nhận thanh toán"
    except Exception as e:
        session.rollback()
        return False, f"Lỗi thanh toán: {e}"

# ============================================================
# TRẢ HÀNG
# ============================================================
def create_return(
    session: Session, data: ReturnCreate,
    user_id: Optional[int] = None,
) -> Tuple[Optional[SaleReturn], str]:
    """Tạo phiếu trả hàng, nhập lại kho với GIÁ VỐN GỐC."""
    try:
        total = 0.0
        code = _gen_code(session, SaleReturn, "TH")
        shift = get_open_shift(session, user_id)

        # Xác định loại khách hàng để tìm giá vốn phù hợp
        customer_type = "RETAIL"
        if data.customer_id:
            cust = session.get(Customer, data.customer_id)
            if cust:
                customer_type = cust.customer_type

        ret = SaleReturn(
            code=code,
            original_order_id=data.original_order_id,
            customer_id=data.customer_id,
            shift_id=shift.id if shift else None,
            user_id=user_id,
            status="DRAFT",
            refund_method=data.refund_method,
            reason=data.reason,
            note=data.note,
        )
        session.add(ret)
        session.flush()

        for l in data.lines:
            # Quy đổi UoM → base
            base_qty = l.quantity
            if l.uom_id:
                uom = session.get(ProductUoM, l.uom_id)
                if uom:
                    base_qty = l.quantity * uom.factor

            refund = l.quantity * l.unit_price
            total += refund

            # ==== TÌM GIÁ VỐN GỐC ====
            cost_price = 0.0
            # Ưu tiên 1: Từ đơn gốc
            if data.original_order_id:
                orig_line = session.exec(
                    select(SaleOrderLine)
                    .where(SaleOrderLine.order_id == data.original_order_id)
                    .where(SaleOrderLine.product_id == l.product_id)
                ).first()
                if orig_line and orig_line.cost_price_at_sale > 0:
                    cost_price = orig_line.cost_price_at_sale

            # Ưu tiên 2: Tìm từ lịch sử bán hàng
            if cost_price == 0:
                cost_price = _find_last_cost_price(
                    session, l.product_id, customer_type
                )

            # Fallback cuối: dùng giá hiện tại của sản phẩm
            if cost_price == 0:
                p = session.get(Product, l.product_id)
                if p:
                    cost_price = p.cost_price

            # Nhập lại kho với giá vốn gốc
            try:
                move = kho_services.create_stock_move(session, StockMoveCreateFull(
                    product_id=l.product_id,
                    quantity=base_qty,
                    unit_price=cost_price,  # ← GIÁ VỐN, không phải giá bán
                    move_type="IN",
                    uom_id=l.uom_id,
                    uom_quantity=l.quantity,
                    note=f"Trả hàng {code} - giá vốn gốc",
                ))
            except ValueError as e:
                session.rollback()
                return None, f"Lỗi nhập kho: {e}"

            line = SaleReturnLine(
                return_id=ret.id,
                product_id=l.product_id,
                uom_id=l.uom_id,
                quantity=l.quantity,
                base_quantity=base_qty,
                unit_price=l.unit_price,      # Giá bán (để hoàn tiền khách)
                refund_amount=refund,
                cost_price=cost_price,        # Giá vốn (để tracking lợi nhuận)
                reason=l.reason,
                stock_move_id=move.id,
            )
            session.add(line)

        ret.total_amount = total
        ret.status = "CONFIRMED"

        # Cập nhật công nợ / hoàn tiền
        if data.customer_id:
            cust = session.get(Customer, data.customer_id)
            if cust:
                if data.refund_method == "CREDIT_NOTE":
                    # Trừ vào công nợ
                    cust.current_debt -= total
                    if cust.current_debt < 0:
                        cust.current_debt = 0
                    session.add(cust)
                # CASH → đã hoàn tiền mặt, không ảnh hưởng công nợ

        session.add(ret)
        session.commit()
        session.refresh(ret)
        return ret, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo phiếu trả: {e}"


def get_return(session: Session, rid: int) -> Optional[SaleReturn]:
    return session.get(SaleReturn, rid)


def get_return_lines(session: Session, rid: int) -> List[SaleReturnLine]:
    return list(session.exec(
        select(SaleReturnLine).where(SaleReturnLine.return_id == rid)
    ).all())


def get_all_returns(session: Session, limit: int = 100) -> List[SaleReturn]:
    return list(session.exec(
        select(SaleReturn).order_by(SaleReturn.created_at.desc()).limit(limit)
    ).all())


# ============================================================
# BÁO CÁO CƠ BẢN
# ============================================================
def report_daily_revenue(session: Session, date_from: datetime, date_to: datetime):
    """Doanh thu theo ngày."""
    orders = session.exec(
        select(SaleOrder)
        .where(SaleOrder.created_at >= date_from)
        .where(SaleOrder.created_at <= date_to)
        .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
    ).all()

    # Group by ngày
    by_day = {}
    for o in orders:
        day = o.created_at.strftime("%Y-%m-%d")
        if day not in by_day:
            by_day[day] = {"count": 0, "revenue": 0.0, "discount": 0.0, "tax": 0.0}
        by_day[day]["count"] += 1
        by_day[day]["revenue"] += o.total_amount
        by_day[day]["discount"] += o.discount_amount
        by_day[day]["tax"] += o.tax_amount

    return sorted(by_day.items(), reverse=True)


def report_top_products(session: Session, date_from: datetime, date_to: datetime, limit: int = 10):
    """Top sản phẩm bán chạy."""
    results = session.exec(
        select(
            SaleOrderLine.product_id,
            func.sum(SaleOrderLine.base_quantity).label("total_qty"),
            func.sum(SaleOrderLine.line_total).label("total_revenue"),
        )
        .join(SaleOrder, SaleOrderLine.order_id == SaleOrder.id)
        .where(SaleOrder.created_at >= date_from)
        .where(SaleOrder.created_at <= date_to)
        .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
        .group_by(SaleOrderLine.product_id)
        .order_by(func.sum(SaleOrderLine.base_quantity).desc())
        .limit(limit)
    ).all()

    # Lấy tên SP
    result = []
    for pid, qty, revenue in results:
        p = session.get(Product, pid)
        result.append({
            "product": p,
            "quantity": qty,
            "revenue": revenue,
        })
    return result


def report_profit(session: Session, date_from: datetime, date_to: datetime):
    """Lợi nhuận gộp = Doanh thu - Giá vốn."""
    result = session.exec(
        select(
            func.sum(SaleOrderLine.line_total).label("revenue"),
            func.sum(SaleOrderLine.cost_price_at_sale * SaleOrderLine.base_quantity).label("cost"),
        )
        .join(SaleOrder, SaleOrderLine.order_id == SaleOrder.id)
        .where(SaleOrder.created_at >= date_from)
        .where(SaleOrder.created_at <= date_to)
        .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
    ).first()

    revenue = result[0] or 0.0
    cost = result[1] or 0.0
    return {
        "revenue": revenue,
        "cost": cost,
        "profit": revenue - cost,
        "margin_percent": ((revenue - cost) / revenue * 100) if revenue > 0 else 0,
    }

# ============================================================
# VAT CUSTOMER (danh bạ xuất hóa đơn)
# ============================================================
def lookup_vat_customer(session: Session, tax_code: str) -> Optional[VatCustomer]:
    """Tra cứu khách VAT theo MST."""
    if not tax_code:
        return None
    return session.exec(
        select(VatCustomer).where(VatCustomer.tax_code == tax_code.strip())
    ).first()


def upsert_vat_customer(
    session: Session,
    tax_code: str, company_name: str, address: str = "",
    email: str = "", phone: str = "", customer_id: Optional[int] = None,
) -> Optional[VatCustomer]:
    """Lưu hoặc cập nhật thông tin KH VAT."""
    if not tax_code or not company_name:
        return None

    tax_code = tax_code.strip()
    existing = lookup_vat_customer(session, tax_code)

    now = datetime.now(timezone.utc)

    if existing:
        # Cập nhật
        existing.company_name = company_name
        existing.address = address or existing.address
        existing.email = email or existing.email
        existing.phone = phone or existing.phone
        if customer_id:
            existing.customer_id = customer_id
        existing.used_count += 1
        existing.last_used_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    else:
        # Tạo mới
        vc = VatCustomer(
            tax_code=tax_code,
            company_name=company_name,
            address=address,
            email=email,
            phone=phone,
            customer_id=customer_id,
            used_count=1,
            created_at=now,
            last_used_at=now,
        )
        session.add(vc)
        session.commit()
        session.refresh(vc)
        return vc