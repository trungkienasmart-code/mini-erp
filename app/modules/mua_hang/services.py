# app/modules/mua_hang/services.py
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from sqlmodel import Session, select, func, or_

from app.modules.mua_hang.models import (
    PurchaseOrder, PurchaseOrderLine, PurchasePayment,
    PurchaseReturn, PurchaseReturnLine,
)
from app.modules.mua_hang.schemas import (
    PurchaseOrderCreate, PurchaseOrderLineCreate,
    ReceiveInput,
    PaymentCreate,
    ReturnCreate,
)
from app.modules.quan_ly_kho.models import (
    Product, ProductUoM, StockMove, StockLayer, Supplier,
)
from app.modules.quan_ly_kho import services as kho_services
from app.modules.quan_ly_kho.schemas import StockMoveCreateFull

# ============================================================
# HELPER: Sinh phiếu chi kế toán
# ============================================================
def _create_payment_voucher(
    session: Session, cash_account_id: int, amount: float,
    reason: str, category: str = "GVHB",
    ref_type: str = "PURCHASE", ref_id: Optional[int] = None,
    partner_name: str = "", voucher_date=None,
) -> Optional[int]:
    """Sinh phiếu chi kế toán. Trả về voucher.id hoặc None nếu lỗi."""
    try:
        from app.modules.ke_toan.services import create_voucher
        from app.modules.ke_toan.schemas import VoucherCreate

        data = VoucherCreate(
            voucher_type="PAYMENT",
            cash_account_id=cash_account_id,
            partner_type="SUPPLIER",
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


def _create_receipt_voucher(
    session: Session, cash_account_id: int, amount: float,
    reason: str, category: str = "KHAC",
    ref_type: str = "PURCHASE_RETURN", ref_id: Optional[int] = None,
    partner_name: str = "", voucher_date=None,
) -> Optional[int]:
    """Sinh phiếu thu (dùng khi NCC hoàn tiền trả hàng)."""
    try:
        from app.modules.ke_toan.services import create_voucher
        from app.modules.ke_toan.schemas import VoucherCreate

        data = VoucherCreate(
            voucher_type="RECEIPT",
            cash_account_id=cash_account_id,
            partner_type="SUPPLIER",
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

# ============================================================
# HELPERS
# ============================================================
def _gen_code(session: Session, model, prefix: str) -> str:
    """Sinh mã tự động: PREFIX + YYMMDD + STT."""
    today = datetime.now().strftime("%y%m%d")
    pattern = f"{prefix}{today}%"
    stmt = select(func.count()).select_from(model).where(model.code.like(pattern))
    count = session.exec(stmt).one() or 0
    return f"{prefix}{today}{count + 1:04d}"


# ============================================================
# SUPPLIER HELPERS
# ============================================================
def get_supplier(session: Session, sid: int) -> Optional[Supplier]:
    return session.get(Supplier, sid)


def get_all_suppliers(session: Session) -> List[Supplier]:
    return list(session.exec(select(Supplier).order_by(Supplier.name)).all())


def get_supplier_debts(session: Session) -> List[dict]:
    """Báo cáo công nợ toàn bộ NCC."""
    sups = session.exec(select(Supplier).order_by(Supplier.current_debt.desc())).all()
    result = []
    for s in sups:
        if s.current_debt <= 0:
            continue
        # Đếm số đơn chưa thanh toán
        unpaid = session.exec(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.supplier_id == s.id)
            .where(PurchaseOrder.status.in_(["RECEIVED", "PARTIAL"]))
        ).one() or 0
        result.append({
            "supplier": s,
            "unpaid_count": unpaid,
            "current_debt": s.current_debt,
        })
    return result


# ============================================================
# PURCHASE ORDER — TÍNH TOÁN
# ============================================================
def _calc_order_totals(lines_data: List[PurchaseOrderLineCreate], discount_amount: float):
    lines = []
    subtotal = 0.0
    total_tax = 0.0

    for l in lines_data:
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
            "base_quantity": l.quantity,
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


# ============================================================
# PURCHASE ORDER — CREATE / UPDATE
# ============================================================
def create_purchase_order(
    session: Session, data: PurchaseOrderCreate,
    user_id: Optional[int] = None,
) -> Tuple[Optional[PurchaseOrder], str]:
    """Tạo đơn mua ở trạng thái DRAFT."""
    try:
        supplier = session.get(Supplier, data.supplier_id)
        if not supplier:
            return None, "Nhà cung cấp không tồn tại"

        totals = _calc_order_totals(data.lines, data.discount_amount)

        # Tính ngày đến hạn
        term_days = supplier.payment_term_days or 30
        due = datetime.now(timezone.utc).date() + timedelta(days=term_days)

        code = _gen_code(session, PurchaseOrder, "PN")

        order = PurchaseOrder(
            code=code,
            supplier_id=data.supplier_id,
            user_id=user_id,
            status="DRAFT",
            subtotal=totals["subtotal"],
            discount_amount=totals["discount_amount"],
            tax_amount=totals["tax_amount"],
            total_amount=totals["total_amount"],
            payment_method=data.payment_method,
            supplier_invoice_no=data.supplier_invoice_no,
            supplier_invoice_date=data.supplier_invoice_date,
            due_date=due,
            note=data.note,
        )
        session.add(order)
        session.flush()

        for ldata in totals["lines"]:
            base_qty = ldata["quantity"]
            if ldata["uom_id"]:
                uom = session.get(ProductUoM, ldata["uom_id"])
                if uom:
                    base_qty = ldata["quantity"] * uom.factor

            line = PurchaseOrderLine(
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
            session.add(line)

        session.commit()
        session.refresh(order)
        return order, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo đơn: {e}"


def get_order(session: Session, oid: int) -> Optional[PurchaseOrder]:
    return session.get(PurchaseOrder, oid)


def get_order_lines(session: Session, oid: int) -> List[PurchaseOrderLine]:
    return list(session.exec(
        select(PurchaseOrderLine).where(PurchaseOrderLine.order_id == oid)
    ).all())


def get_order_payments(session: Session, oid: int) -> List[PurchasePayment]:
    return list(session.exec(
        select(PurchasePayment).where(PurchasePayment.order_id == oid)
    ).all())


def get_all_orders(
    session: Session,
    keyword: str = "",
    status: str = "",
    supplier_id: Optional[int] = None,
    limit: int = 200,
) -> List[PurchaseOrder]:
    stmt = select(PurchaseOrder)
    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(PurchaseOrder.code.like(p))
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    stmt = stmt.order_by(PurchaseOrder.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


# ============================================================
# APPROVE
# ============================================================
def approve_order(session: Session, oid: int) -> Tuple[bool, str]:
    """Duyệt đơn mua → APPROVED."""
    order = session.get(PurchaseOrder, oid)
    if not order:
        return False, "Đơn không tồn tại"
    if order.status != "DRAFT":
        return False, f"Chỉ duyệt được đơn DRAFT (hiện tại: {order.status})"

    order.status = "APPROVED"
    order.approved_at = datetime.now(timezone.utc)
    session.add(order)
    session.commit()
    return True, "Đã duyệt đơn"


def mark_email_sent(session: Session, oid: int, email_to: str) -> Tuple[bool, str]:
    """Đánh dấu đã gửi email cho NCC."""
    order = session.get(PurchaseOrder, oid)
    if not order:
        return False, "Đơn không tồn tại"
    order.email_sent_at = datetime.now(timezone.utc)
    order.email_sent_to = email_to
    session.add(order)
    session.commit()
    return True, "Đã đánh dấu gửi email"


# ============================================================
# RECEIVE (Nhận hàng + Nhập kho)
# ============================================================
def receive_order(
    session: Session, data: ReceiveInput,
    user_id: Optional[int] = None,
) -> Tuple[Optional[PurchaseOrder], str]:
    """
    Nhận hàng:
    - Nếu có order_id: cập nhật đơn cũ sang RECEIVED
    - Nếu không: tạo đơn mới với trạng thái RECEIVED
    """
    try:
        # Case 1: Nhận theo đơn
        if data.order_id:
            order = session.get(PurchaseOrder, data.order_id)
            if not order:
                return None, "Đơn không tồn tại"
            if order.status not in ("DRAFT", "APPROVED"):
                return None, f"Không thể nhận đơn ở trạng thái {order.status}"

            # Cập nhật thông tin hóa đơn NCC
            if data.supplier_invoice_no:
                order.supplier_invoice_no = data.supplier_invoice_no
            if data.supplier_invoice_date:
                order.supplier_invoice_date = data.supplier_invoice_date

            # Xử lý từng dòng
            for item in data.lines:
                base_qty = item.quantity
                if item.uom_id:
                    uom = session.get(ProductUoM, item.uom_id)
                    if uom:
                        base_qty = item.quantity * uom.factor

                # Nhập kho
                try:
                    move = kho_services.create_stock_move(session, StockMoveCreateFull(
                        product_id=item.product_id,
                        quantity=base_qty,
                        unit_price=item.unit_price,
                        move_type="IN",
                        uom_id=item.uom_id,
                        uom_quantity=item.quantity,
                        note=f"Nhập theo đơn {order.code}",
                    ))
                except ValueError as e:
                    session.rollback()
                    return None, f"Lỗi nhập kho: {e}"

                # Cập nhật line
                if item.line_id:
                    line = session.get(PurchaseOrderLine, item.line_id)
                    if line:
                        line.received_quantity = item.quantity
                        line.stock_move_id = move.id
                        session.add(line)

            # Cập nhật tổng tiền theo thực tế (nếu user đã sửa)
            _recalc_order_total(session, order)

            order.status = "RECEIVED"

            # Tăng công nợ NCC
            supplier = session.get(Supplier, order.supplier_id)
            if supplier:
                supplier.current_debt += order.total_amount
                session.add(supplier)

            session.add(order)
            session.commit()
            session.refresh(order)
            return order, "OK"

        # Case 2: Nhập nhanh không theo đơn
        else:
            if not data.supplier_id:
                return None, "Phải chọn nhà cung cấp"

            supplier = session.get(Supplier, data.supplier_id)
            if not supplier:
                return None, "Nhà cung cấp không tồn tại"

            # Tạo đơn mới trực tiếp với status RECEIVED
            code = _gen_code(session, PurchaseOrder, "PN")
            term_days = supplier.payment_term_days or 30
            due = datetime.now(timezone.utc).date() + timedelta(days=term_days)

            order = PurchaseOrder(
                code=code,
                supplier_id=data.supplier_id,
                user_id=user_id,
                status="RECEIVED",
                payment_method="DEBT",
                supplier_invoice_no=data.supplier_invoice_no,
                supplier_invoice_date=data.supplier_invoice_date,
                due_date=due,
                note=data.note,
            )
            session.add(order)
            session.flush()

            subtotal = 0.0
            total_tax = 0.0

            for item in data.lines:
                base_qty = item.quantity
                if item.uom_id:
                    uom = session.get(ProductUoM, item.uom_id)
                    if uom:
                        base_qty = item.quantity * uom.factor

                # Nhập kho
                try:
                    move = kho_services.create_stock_move(session, StockMoveCreateFull(
                        product_id=item.product_id,
                        quantity=base_qty,
                        unit_price=item.unit_price,
                        move_type="IN",
                        uom_id=item.uom_id,
                        uom_quantity=item.quantity,
                        note=f"Nhập nhanh {code}",
                    ))
                except ValueError as e:
                    session.rollback()
                    return None, f"Lỗi nhập kho: {e}"

                line_amount = item.quantity * item.unit_price
                line_tax = line_amount * item.tax_rate / 100
                subtotal += line_amount
                total_tax += line_tax

                line = PurchaseOrderLine(
                    order_id=order.id,
                    product_id=item.product_id,
                    uom_id=item.uom_id,
                    quantity=item.quantity,
                    base_quantity=base_qty,
                    unit_price=item.unit_price,
                    tax_rate=item.tax_rate,
                    line_subtotal=line_amount,
                    line_tax=line_tax,
                    line_total=line_amount + line_tax,
                    received_quantity=item.quantity,
                    stock_move_id=move.id,
                )
                session.add(line)

            order.subtotal = subtotal
            order.tax_amount = total_tax
            order.total_amount = subtotal + total_tax
            session.add(order)

            # Tăng công nợ NCC
            supplier.current_debt += order.total_amount
            session.add(supplier)

            session.commit()
            session.refresh(order)
            return order, "OK"

    except Exception as e:
        session.rollback()
        return None, f"Lỗi nhận hàng: {e}"


def _recalc_order_total(session: Session, order: PurchaseOrder):
    """Tính lại tổng tiền đơn mua theo received_quantity."""
    lines = session.exec(
        select(PurchaseOrderLine).where(PurchaseOrderLine.order_id == order.id)
    ).all()
    subtotal = 0.0
    tax = 0.0
    for l in lines:
        if l.received_quantity > 0:
            amt = l.received_quantity * l.unit_price
            subtotal += amt
            tax += amt * l.tax_rate / 100
    order.subtotal = subtotal
    order.tax_amount = tax
    order.total_amount = subtotal + tax
    session.add(order)


# ============================================================
# PAYMENT
# ============================================================
def add_payment(session: Session, data: PaymentCreate) -> Tuple[bool, str]:
    try:
        order = session.get(PurchaseOrder, data.order_id)
        if not order:
            return False, "Đơn không tồn tại"
        if order.status == "CANCELLED":
            return False, "Đơn đã hủy"
        if order.status == "PAID":
            return False, "Đơn đã thanh toán đủ"

        remaining = order.total_amount - order.paid_amount
        if data.amount > remaining + 0.01:
            return False, f"Số tiền vượt quá còn lại ({remaining:,.0f}đ)"

        payment = PurchasePayment(
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
        elif order.status == "RECEIVED":
            order.status = "PARTIAL"

        # Giảm công nợ NCC
        supplier = session.get(Supplier, order.supplier_id)
        if supplier:
            supplier.current_debt -= data.amount
            if supplier.current_debt < 0:
                supplier.current_debt = 0
            session.add(supplier)

        session.add(order)

        # Sinh phiếu chi nếu có chọn tài khoản quỹ
        if data.cash_account_id:
            _create_payment_voucher(
                session, data.cash_account_id, data.amount,
                reason=f"Trả tiền đơn mua {order.code}" + (f" - {data.note}" if data.note else ""),
                category="GVHB",
                ref_type="PURCHASE", ref_id=order.id,
                partner_name=supplier.name if supplier else "",
            )

        session.commit()
        return True, "Đã ghi nhận thanh toán"
    except Exception as e:
        session.rollback()
        return False, f"Lỗi thanh toán: {e}"

# ============================================================
# CANCEL ORDER
# ============================================================
def cancel_order(session: Session, oid: int) -> Tuple[bool, str]:
    order = session.get(PurchaseOrder, oid)
    if not order:
        return False, "Đơn không tồn tại"
    if order.status not in ("DRAFT", "APPROVED"):
        return False, f"Không hủy được đơn ở trạng thái {order.status}"
    if order.paid_amount > 0:
        return False, "Đơn đã thanh toán, không thể hủy"

    order.status = "CANCELLED"
    session.add(order)
    session.commit()
    return True, "Đã hủy đơn"


# ============================================================
# RETURN TO SUPPLIER (3 bước)
# ============================================================
def create_return(
    session: Session, data: ReturnCreate,
    user_id: Optional[int] = None,
) -> Tuple[Optional[PurchaseReturn], str]:
    """Tạo phiếu trả NCC ở trạng thái DRAFT."""
    try:
        supplier = session.get(Supplier, data.supplier_id)
        if not supplier:
            return None, "Nhà cung cấp không tồn tại"

        code = _gen_code(session, PurchaseReturn, "THM")
        ret = PurchaseReturn(
            code=code,
            supplier_id=data.supplier_id,
            original_order_id=data.original_order_id,
            user_id=user_id,
            status="DRAFT",
            refund_method=data.refund_method,
            reason=data.reason,
            note=data.note,
        )
        session.add(ret)
        session.flush()

        total = 0.0
        for l in data.lines:
            base_qty = l.quantity
            if l.uom_id:
                uom = session.get(ProductUoM, l.uom_id)
                if uom:
                    base_qty = l.quantity * uom.factor

            refund = l.quantity * l.unit_price
            total += refund

            line = PurchaseReturnLine(
                return_id=ret.id,
                product_id=l.product_id,
                uom_id=l.uom_id,
                stock_layer_id=l.stock_layer_id,
                quantity=l.quantity,
                base_quantity=base_qty,
                unit_price=l.unit_price,
                refund_amount=refund,
                reason=l.reason,
            )
            session.add(line)

        ret.total_amount = total
        session.add(ret)
        session.commit()
        session.refresh(ret)
        return ret, "OK"
    except Exception as e:
        session.rollback()
        return None, f"Lỗi tạo phiếu trả: {e}"


def approve_return(session: Session, rid: int) -> Tuple[bool, str]:
    ret = session.get(PurchaseReturn, rid)
    if not ret:
        return False, "Phiếu không tồn tại"
    if ret.status != "DRAFT":
        return False, f"Chỉ duyệt được phiếu DRAFT"
    ret.status = "APPROVED"
    ret.approved_at = datetime.now(timezone.utc)
    session.add(ret)
    session.commit()
    return True, "Đã duyệt phiếu trả"


def confirm_return(
    session: Session, rid: int,
    signature_note: str = "", note: str = "",
) -> Tuple[bool, str]:
    """Xác nhận trả hàng thực tế → xuất kho + giảm công nợ."""
    try:
        ret = session.get(PurchaseReturn, rid)
        if not ret:
            return False, "Phiếu không tồn tại"
        if ret.status != "APPROVED":
            return False, "Phải duyệt phiếu trước khi xác nhận"

        # Xuất kho từng dòng
        lines = session.exec(
            select(PurchaseReturnLine).where(PurchaseReturnLine.return_id == rid)
        ).all()

        for line in lines:
            try:
                move = kho_services.create_stock_move(session, StockMoveCreateFull(
                    product_id=line.product_id,
                    quantity=line.base_quantity,
                    unit_price=line.unit_price,
                    move_type="OUT",
                    uom_id=line.uom_id,
                    uom_quantity=line.quantity,
                    export_reason="TRẢ NCC",
                    note=f"Trả NCC theo phiếu {ret.code}",
                ))
                line.stock_move_id = move.id
                session.add(line)
            except ValueError as e:
                session.rollback()
                return False, f"Lỗi xuất kho: {e}"

        # Giảm công nợ NCC
        if ret.refund_method == "CREDIT":
            supplier = session.get(Supplier, ret.supplier_id)
            if supplier:
                supplier.current_debt -= ret.total_amount
                if supplier.current_debt < 0:
                    supplier.current_debt = 0
                session.add(supplier)

        ret.status = "CONFIRMED"
        ret.signature_note = signature_note
        ret.confirmed_at = datetime.now(timezone.utc)
        if note:
            ret.note = (ret.note + "\n" + note).strip()

        session.add(ret)
        session.commit()
        return True, "Đã xác nhận trả hàng và xuất kho"
    except Exception as e:
        session.rollback()
        return False, f"Lỗi xác nhận: {e}"


def mark_return_email_sent(session: Session, rid: int, email_to: str) -> Tuple[bool, str]:
    ret = session.get(PurchaseReturn, rid)
    if not ret:
        return False, "Phiếu không tồn tại"
    ret.email_sent_at = datetime.now(timezone.utc)
    ret.email_sent_to = email_to
    session.add(ret)
    session.commit()
    return True, "Đã đánh dấu gửi email"


def get_return(session: Session, rid: int) -> Optional[PurchaseReturn]:
    return session.get(PurchaseReturn, rid)


def get_return_lines(session: Session, rid: int) -> List[PurchaseReturnLine]:
    return list(session.exec(
        select(PurchaseReturnLine).where(PurchaseReturnLine.return_id == rid)
    ).all())


def get_all_returns(
    session: Session, keyword: str = "", status: str = "", limit: int = 100,
) -> List[PurchaseReturn]:
    stmt = select(PurchaseReturn)
    if keyword:
        p = f"%{keyword}%"
        stmt = stmt.where(PurchaseReturn.code.like(p))
    if status:
        stmt = stmt.where(PurchaseReturn.status == status)
    stmt = stmt.order_by(PurchaseReturn.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


# ============================================================
# STOCK LAYERS BY SUPPLIER (cho form trả hàng)
# ============================================================
def get_stock_layers_by_product_and_supplier(
    session: Session, product_id: int, supplier_id: int,
) -> List[dict]:
    """
    Lấy các lô nhập còn hàng của sản phẩm, filter theo NCC.
    """
    # Lấy tất cả stock_moves nhập từ NCC này
    moves = session.exec(
        select(StockMove)
        .where(StockMove.product_id == product_id)
        .where(StockMove.move_type == "IN")
    ).all()

    # Map move_id → supplier (thông qua PurchaseOrderLine → PurchaseOrder)
    move_to_supplier = {}
    for move in moves:
        po_line = session.exec(
            select(PurchaseOrderLine).where(PurchaseOrderLine.stock_move_id == move.id)
        ).first()
        if po_line:
            po = session.get(PurchaseOrder, po_line.order_id)
            if po:
                move_to_supplier[move.id] = po.supplier_id

    # Lấy layers còn hàng
    layers = session.exec(
        select(StockLayer)
        .where(StockLayer.product_id == product_id)
        .where(StockLayer.remaining_qty > 0)
        .order_by(StockLayer.created_at.desc())
    ).all()

    result = []
    for layer in layers:
        sup_id = move_to_supplier.get(layer.stock_move_id)
        if sup_id == supplier_id:
            result.append({
                "id": layer.id,
                "initial_qty": layer.initial_qty,
                "remaining_qty": layer.remaining_qty,
                "unit_cost": layer.unit_cost,
                "created_at": layer.created_at,
            })
    return result


# ============================================================
# EXPORT CSV
# ============================================================
def export_orders_csv(session: Session, status: str = "") -> str:
    import io, csv
    orders = get_all_orders(session, status=status)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Mã đơn", "Ngày", "NCC", "Trạng thái", "Tổng tiền",
                     "Đã trả", "Còn lại", "Số HĐ NCC", "Ngày HĐ"])

    for o in orders:
        sup = session.get(Supplier, o.supplier_id)
        writer.writerow([
            o.code,
            o.created_at.strftime("%Y-%m-%d %H:%M"),
            sup.name if sup else "N/A",
            o.status,
            f"{o.total_amount:.0f}",
            f"{o.paid_amount:.0f}",
            f"{o.total_amount - o.paid_amount:.0f}",
            o.supplier_invoice_no,
            o.supplier_invoice_date.strftime("%Y-%m-%d") if o.supplier_invoice_date else "",
        ])
    return "\ufeff" + output.getvalue()


def export_receives_csv(session: Session) -> str:
    import io, csv
    orders = session.exec(
        select(PurchaseOrder)
        .where(PurchaseOrder.status.in_(["RECEIVED", "PAID", "PARTIAL"]))
        .order_by(PurchaseOrder.created_at.desc())
    ).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Mã đơn", "Ngày nhập", "NCC", "Tổng tiền",
                     "Số HĐ NCC", "Ngày HĐ", "Đến hạn"])
    for o in orders:
        sup = session.get(Supplier, o.supplier_id)
        writer.writerow([
            o.code,
            o.created_at.strftime("%Y-%m-%d %H:%M"),
            sup.name if sup else "N/A",
            f"{o.total_amount:.0f}",
            o.supplier_invoice_no,
            o.supplier_invoice_date.strftime("%Y-%m-%d") if o.supplier_invoice_date else "",
            o.due_date.strftime("%Y-%m-%d") if o.due_date else "",
        ])
    return "\ufeff" + output.getvalue()