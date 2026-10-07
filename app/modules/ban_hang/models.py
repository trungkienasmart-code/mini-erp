# app/modules/ban_hang/models.py
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# KHÁCH HÀNG
# ============================================================
class Customer(SQLModel, table=True):
    __tablename__ = "sale_customer"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=200)
    phone: str = Field(default="", max_length=30, index=True)
    email: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=300)
    tax_code: str = Field(default="", max_length=30)
    customer_type: str = Field(default="RETAIL", max_length=20)  # RETAIL / WHOLESALE
    credit_limit: float = Field(default=0.0)
    current_debt: float = Field(default=0.0)
    loyalty_points: int = Field(default=0)  # Điểm tích lũy (cho CRM sau này)
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# MÃ GIẢM GIÁ
# ============================================================
class SaleDiscountCode(SQLModel, table=True):
    __tablename__ = "sale_discount_code"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=200)
    discount_type: str = Field(default="PERCENT", max_length=20)  # PERCENT / AMOUNT
    discount_value: float = Field(default=0.0)
    max_discount: float = Field(default=0.0)  # Chỉ áp dụng nếu PERCENT
    min_order_amount: float = Field(default=0.0)

    # Phạm vi áp dụng
    apply_to: str = Field(default="ALL", max_length=20)  # ALL / CATEGORY / PRODUCT
    category_id: Optional[int] = Field(default=None, foreign_key="inv_category.id")
    product_id: Optional[int] = Field(default=None, foreign_key="inv_product.id")

    # Điều kiện thời gian & số lần dùng
    valid_from: Optional[datetime] = Field(default=None)
    valid_to: Optional[datetime] = Field(default=None)
    max_uses: int = Field(default=0)  # 0 = không giới hạn
    used_count: int = Field(default=0)

    # Kiểm soát
    requires_approval: bool = Field(default=False)  # Cần user cấp cao duyệt
    status: str = Field(default="ACTIVE", max_length=20)  # ACTIVE / INACTIVE
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# CA LÀM VIỆC (SHIFT)
# ============================================================
class SaleShift(SQLModel, table=True):
    __tablename__ = "sale_shift"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    user_id: Optional[int] = Field(default=None, index=True)  # Cho phân quyền sau

    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = Field(default=None)

    opening_cash: float = Field(default=0.0)  # Tiền lẻ đầu ca

    # Tổng hợp doanh thu theo phương thức (cập nhật khi đóng ca)
    total_cash_sales: float = Field(default=0.0)
    total_bank_sales: float = Field(default=0.0)
    total_card_sales: float = Field(default=0.0)
    total_debt_sales: float = Field(default=0.0)
    total_returns: float = Field(default=0.0)
    total_revenue: float = Field(default=0.0)

    # Kiểm đếm tiền mặt
    counted_cash: float = Field(default=0.0)  # Tiền đếm thực tế
    cash_difference: float = Field(default=0.0)  # Chênh lệch

    # Tài khoản quỹ nhận tiền khi kết ca
    cash_account_id: Optional[int] = Field(default=None, foreign_key="acc_cash_account.id")
    bank_account_id: Optional[int] = Field(default=None, foreign_key="acc_cash_account.id")
    shift_receipt_ids: str = Field(default="", max_length=500)  # JSON list các voucher id

    status: str = Field(default="OPEN", max_length=20)  # OPEN / CLOSED
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SaleShiftDenomination(SQLModel, table=True):
    __tablename__ = "sale_shift_denomination"

    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(foreign_key="sale_shift.id", index=True)
    denomination: int = Field(default=0)  # Mệnh giá (500000, 200000, ...)
    quantity: int = Field(default=0)
    subtotal: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# ĐƠN BÁN HÀNG (POS + INVOICE)
# ============================================================
class SaleOrder(SQLModel, table=True):
    __tablename__ = "sale_order"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="sale_customer.id", index=True)
    shift_id: Optional[int] = Field(default=None, foreign_key="sale_shift.id", index=True)
    discount_code_id: Optional[int] = Field(default=None, foreign_key="sale_discount_code.id")
    user_id: Optional[int] = Field(default=None, index=True)  # Cho phân quyền sau

    order_type: str = Field(default="POS", max_length=20)  # POS / INVOICE
    status: str = Field(default="DRAFT", max_length=20)
    # DRAFT / CONFIRMED / PAID / PARTIAL / CANCELLED / RETURNED

    # Tiền
    subtotal: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    tax_amount: float = Field(default=0.0)
    total_amount: float = Field(default=0.0)
    paid_amount: float = Field(default=0.0)
    customer_paid: float = Field(default=0.0)   # Số tiền khách đưa (POS)
    change_amount: float = Field(default=0.0)   # Tiền thối lại khách

    # Thanh toán
    payment_method: str = Field(default="CASH", max_length=20)  # CASH / BANK / CARD / DEBT / MIXED

    # Thông tin VAT (dùng cho POS, khách yêu cầu xuất hóa đơn)
    want_vat_invoice: bool = Field(default=False)
    vat_company_name: str = Field(default="", max_length=200)
    vat_tax_code: str = Field(default="", max_length=30)
    vat_address: str = Field(default="", max_length=300)
    vat_email: str = Field(default="", max_length=100)

    # SĐT khách (nếu chưa có trong DB — cho CRM)
    customer_phone: str = Field(default="", max_length=30)

    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    lines: List["SaleOrderLine"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    payments: List["SalePayment"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SaleOrderLine(SQLModel, table=True):
    __tablename__ = "sale_order_line"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="sale_order.id", index=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)
    uom_id: Optional[int] = Field(default=None, foreign_key="inv_product_uom.id")

    quantity: int = Field(default=0)  # Theo UoM
    base_quantity: int = Field(default=0)  # Theo base unit
    unit_price: float = Field(default=0.0)  # Đơn giá theo UoM

    discount_percent: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    tax_rate: float = Field(default=0.0)

    line_subtotal: float = Field(default=0.0)  # qty × price - discount
    line_tax: float = Field(default=0.0)
    line_total: float = Field(default=0.0)

    cost_price_at_sale: float = Field(default=0.0)  # Giá vốn tại thời điểm bán
    stock_move_id: Optional[int] = Field(default=None, foreign_key="inv_stock_move.id")

    order: Optional[SaleOrder] = Relationship(back_populates="lines")


class SalePayment(SQLModel, table=True):
    __tablename__ = "sale_payment"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="sale_order.id", index=True)
    amount: float = Field(default=0.0)
    payment_method: str = Field(default="CASH", max_length=20)

    # Cho thanh toán CK (tương lai kết nối API ngân hàng)
    bank_transaction_code: str = Field(default="", max_length=100)
    bank_verified: bool = Field(default=False)
    cash_account_id: Optional[int] = Field(default=None, foreign_key="acc_cash_account.id")
    note: str = Field(default="", max_length=300)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    order: Optional[SaleOrder] = Relationship(back_populates="payments")


# ============================================================
# TRẢ HÀNG
# ============================================================
class SaleReturn(SQLModel, table=True):
    __tablename__ = "sale_return"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    original_order_id: Optional[int] = Field(default=None, foreign_key="sale_order.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="sale_customer.id")
    shift_id: Optional[int] = Field(default=None, foreign_key="sale_shift.id")
    user_id: Optional[int] = Field(default=None, index=True)

    status: str = Field(default="DRAFT", max_length=20)  # DRAFT / CONFIRMED
    total_amount: float = Field(default=0.0)
    refund_method: str = Field(default="CASH", max_length=20)  # CASH / BANK / CREDIT_NOTE

    reason: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    lines: List["SaleReturnLine"] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SaleReturnLine(SQLModel, table=True):
    __tablename__ = "sale_return_line"

    id: Optional[int] = Field(default=None, primary_key=True)
    return_id: int = Field(foreign_key="sale_return.id", index=True)
    product_id: int = Field(foreign_key="inv_product.id")
    uom_id: Optional[int] = Field(default=None, foreign_key="inv_product_uom.id")

    quantity: int = Field(default=0)
    base_quantity: int = Field(default=0)
    unit_price: float = Field(default=0.0)  # Giá bán ban đầu
    refund_amount: float = Field(default=0.0)
    cost_price: float = Field(default=0.0)  # Giá vốn để nhập lại kho

    reason: str = Field(default="", max_length=300)
    stock_move_id: Optional[int] = Field(default=None, foreign_key="inv_stock_move.id")

# ============================================================
# KHÁCH XUẤT HÓA ĐƠN VAT (danh bạ tra cứu nhanh)
# ============================================================
class VatCustomer(SQLModel, table=True):
    __tablename__ = "sale_vat_customer"

    id: Optional[int] = Field(default=None, primary_key=True)
    tax_code: str = Field(max_length=30, index=True, unique=True)
    company_name: str = Field(max_length=200)
    address: str = Field(default="", max_length=300)
    email: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=30)

    # Liên kết CRM (optional)
    customer_id: Optional[int] = Field(default=None, foreign_key="sale_customer.id")

    used_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))