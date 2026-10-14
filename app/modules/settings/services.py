# app/modules/settings/services.py
import hmac
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional, Tuple, List
from urllib.parse import quote

from sqlmodel import Session, select

from app.modules.ke_toan.models import HKDProfile, BankTransaction


# ============================================================
# DANH SÁCH NGÂN HÀNG VIỆT NAM (cho VietQR)
# ============================================================
VN_BANKS = {
    "VCB": "Vietcombank",
    "TCB": "Techcombank",
    "MB": "MBBank",
    "VPB": "VPBank",
    "ACB": "ACB",
    "BIDV": "BIDV",
    "VTB": "VietinBank",
    "STB": "Sacombank",
    "TPB": "TPBank",
    "VIB": "VIB",
    "MSB": "MSB",
    "OCB": "OCB",
    "SHB": "SHB",
    "SCB": "SCB",
    "HDB": "HDBank",
    "LPB": "LPBank",
    "EIB": "Eximbank",
    "NAB": "NamABank",
    "SEAB": "SeABank",
    "PVCB": "PVcomBank",
    "AGRIBANK": "Agribank",
    "VIETBANK": "VietBank",
    "NCB": "NCB",
    "BAOVIETBANK": "BaoVietBank",
    "SAIGONBANK": "SaigonBank",
    "ABBANK": "ABBank",
    "SHBVN": "Shinhan Bank VN",
}

WEBHOOK_PROVIDERS = {
    "NONE": "Không kết nối",
    "CASSO": "Casso (casso.vn)",
    "SEPAY": "Sepay (sepay.vn)",
    "PAYOS": "PayOS (payos.vn)",
    "MANUAL": "Nhập tay (không tự động)",
}


# ============================================================
# VIETQR
# ============================================================
def build_vietqr_url(
    bank_code: str,
    account_no: str,
    account_name: str,
    amount: float = 0,
    description: str = "",
    template: str = "compact2",
) -> str:
    """
    Tạo URL ảnh QR theo chuẩn VietQR (Napas).
    Tham khảo: https://vietqr.io/danh-sach-api/link-tao-ma-nhanh/
    """
    if not bank_code or not account_no:
        return ""

    base = f"https://img.vietqr.io/image/{bank_code}-{account_no}-{template}.png"

    params = []
    if amount > 0:
        params.append(f"amount={int(amount)}")
    if description:
        params.append(f"addInfo={quote(description)}")
    if account_name:
        params.append(f"accountName={quote(account_name)}")

    if params:
        base += "?" + "&".join(params)

    return base


def get_bank_name(bank_code: str) -> str:
    return VN_BANKS.get(bank_code, bank_code)


# ============================================================
# PARSE NỘI DUNG CK ĐỂ TÌM MÃ ĐƠN
# ============================================================
def extract_order_code(content: str) -> Optional[str]:
    """
    Trích xuất mã đơn hàng từ nội dung CK.
    Hỗ trợ các format:
      - "Thanh toan HD POS2610080003"
      - "POS2610080003"
      - "TT POS2610080003"
      - "Thanh toan don hang POS2610080003"
    """
    if not content:
        return None

    # Regex tìm mã: POS + 8 số, hoặc HD + 8 số, hoặc NB + ...
    patterns = [
        r"\b(POS\d{10})\b",   # POS + YYMMDD + 4 số
        r"\b(HD\d{10})\b",
        r"\b(TH\d{10})\b",
        r"\b(PN\d{10})\b",
        r"\b(NB\d{10})\b",
        r"\b([A-Z]{2,4}\d{8,12})\b",  # Fallback: chữ+số
    ]

    for pattern in patterns:
        m = re.search(pattern, content.upper())
        if m:
            return m.group(1)

    return None


# ============================================================
# WEBHOOK SIGNATURE VERIFY
# ============================================================
def verify_casso_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 cho Casso."""
    if not signature or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_sepay_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify cho Sepay (dùng HMAC-SHA256)."""
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook(
    provider: str, payload: bytes, signature: str, secret: str,
) -> bool:
    """Verify signature theo provider."""
    if provider == "CASSO":
        return verify_casso_signature(payload, signature, secret)
    elif provider == "SEPAY":
        return verify_sepay_signature(payload, signature, secret)
    elif provider == "PAYOS":
        # PayOS dùng checksum key khác, tạm để TODO
        return True  # Placeholder
    return True  # Provider khác → không verify


# ============================================================
# XỬ LÝ WEBHOOK
# ============================================================
def process_webhook_transaction(
    session: Session,
    transaction_id: str,
    bank_code: str,
    account_no: str,
    amount: float,
    content: str,
    transaction_date: Optional[datetime] = None,
    raw_data: dict = None,
) -> Tuple[Optional[BankTransaction], str]:
    """
    Xử lý 1 giao dịch CK vào.
    1. Lưu vào BankTransaction
    2. Tìm mã đơn từ content
    3. Nếu khớp → cập nhật đơn bán
    """
    # Check trùng lặp
    existing = session.exec(
        select(BankTransaction).where(
            BankTransaction.transaction_id == transaction_id
        )
    ).first()
    if existing:
        return existing, "Đã xử lý rồi"

    txn = BankTransaction(
        transaction_id=transaction_id,
        bank_code=bank_code,
        account_no=account_no,
        amount=amount,
        content=content,
        transaction_date=transaction_date or datetime.now(timezone.utc),
        raw_data=json.dumps(raw_data or {}, ensure_ascii=False)[:2000],
    )

    # Tìm mã đơn
    order_code = extract_order_code(content)

    if not order_code:
        txn.status = "UNMATCHED"
        txn.note = "Không tìm thấy mã đơn trong nội dung"
        session.add(txn)
        session.commit()
        session.refresh(txn)
        return txn, "Không khớp mã đơn"

    # Tìm đơn hàng
    from app.modules.ban_hang.models import SaleOrder, SalePayment, Customer

    order = session.exec(
        select(SaleOrder).where(SaleOrder.code == order_code)
    ).first()

    if not order:
        txn.status = "UNMATCHED"
        txn.matched_order_code = order_code
        txn.note = f"Mã đơn {order_code} không tồn tại"
        session.add(txn)
        session.commit()
        session.refresh(txn)
        return txn, f"Mã đơn không tồn tại"

    txn.matched_order_id = order.id
    txn.matched_order_code = order_code
    txn.matched_at = datetime.now(timezone.utc)

    # Tính còn lại
    remaining = order.total_amount - order.paid_amount

    if abs(amount - remaining) < 1:  # Khớp chính xác
        txn.status = "MATCHED"
        txn.note = "Khớp chính xác"
    elif amount < remaining:
        txn.status = "PARTIAL"
        txn.note = f"Thiếu {remaining - amount:,.0f}đ"
    else:
        txn.status = "MATCHED"
        txn.note = f"Thừa {amount - remaining:,.0f}đ"

    # Tạo payment
    payment = SalePayment(
        order_id=order.id,
        amount=amount,
        payment_method="BANK",
        bank_transaction_code=transaction_id,
        note=f"CK tự động: {content[:100]}",
    )
    session.add(payment)

    order.paid_amount += amount
    if order.paid_amount >= order.total_amount - 0.01:
        order.status = "PAID"
        order.paid_amount = order.total_amount
    else:
        order.status = "PARTIAL"

    # Giảm công nợ KH
    if order.customer_id:
        cust = session.get(Customer, order.customer_id)
        if cust:
            cust.current_debt -= amount
            if cust.current_debt < 0:
                cust.current_debt = 0
            session.add(cust)

    session.add(order)
    session.add(txn)
    session.commit()
    session.refresh(txn)

    return txn, f"Đã khớp đơn {order_code}"


# ============================================================
# POLLING (cho POS)
# ============================================================
def get_recent_bank_transactions(
    session: Session,
    since_seconds: int = 60,
    only_new: bool = True,
) -> List[BankTransaction]:
    """Lấy các giao dịch CK gần đây (để POS poll)."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_seconds)

    stmt = select(BankTransaction).where(
        BankTransaction.created_at >= cutoff
    )

    if only_new:
        stmt = stmt.where(BankTransaction.status == "MATCHED")

    stmt = stmt.order_by(BankTransaction.created_at.desc())
    return list(session.exec(stmt).all())


def get_unmatched_transactions(
    session: Session, limit: int = 100,
) -> List[BankTransaction]:
    """Lấy các giao dịch chưa khớp để kế toán xử lý."""
    return list(session.exec(
        select(BankTransaction)
        .where(BankTransaction.status.in_(["UNMATCHED", "PARTIAL"]))
        .order_by(BankTransaction.created_at.desc())
        .limit(limit)
    ).all())