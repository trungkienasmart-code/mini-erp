# app/modules/mua_hang/models.py
from datetime import datetime, timezone, date
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# ĐƠN MUA HÀNG
# ============================================================
class PurchaseOrder(SQLModel, table=True):
    __tablename__ = "purchase_order"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    supplier_id: int = Field(foreign_key="inv_supplier.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)

    status: str = Field(default="DRAFT", max_length=20)
    # DRAFT / APPROVED / RECEIVED / PAID / PARTIAL / CANCELLED

    # Tiền
    subtotal: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    tax_amount: float = Field(default=0.0)
    total_amount: float = Field(default=0.0)
    paid_amount: float = Field(default=0.0)

    payment_method: str = Field(default="DEBT", max_length=20)

    # Hóa đơn NCC (link kế toán)
    supplier_invoice_no: str = Field(default="", max_length=50)
    supplier_invoice_date: Optional[date] = Field(default=None)

    # Điều khoản thanh toán
    due_date: Optional[date] = Field(default=None)

    # Email
    email_sent_at: Optional[datetime] = Field(default=None)
    email_sent_to: str = Field(default="", max_length=200)

    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    approved_at: Optional[datetime] = Field(default=None)

    lines: List["PurchaseOrderLine"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    payments: List["PurchasePayment"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PurchaseOrderLine(SQLModel, table=True):
    __tablename__ = "purchase_order_line"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="purchase_order.id", index=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)
    uom_id: Optional[int] = Field(default=None, foreign_key="inv_product_uom.id")

    quantity: int = Field(default=0)
    base_quantity: int = Field(default=0)
    unit_price: float = Field(default=0.0)   # Chưa VAT

    discount_percent: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    tax_rate: float = Field(default=0.0)     # VAT đầu vào

    line_subtotal: float = Field(default=0.0)
    line_tax: float = Field(default=0.0)
    line_total: float = Field(default=0.0)

    # Sau khi nhận hàng
    received_quantity: int = Field(default=0)
    stock_move_id: Optional[int] = Field(default=None, foreign_key="inv_stock_move.id")

    order: Optional[PurchaseOrder] = Relationship(back_populates="lines")


class PurchasePayment(SQLModel, table=True):
    __tablename__ = "purchase_payment"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="purchase_order.id", index=True)
    amount: float = Field(default=0.0)
    payment_method: str = Field(default="CASH", max_length=20)

    bank_transaction_code: str = Field(default="", max_length=100)
    cash_account_id: Optional[int] = Field(default=None, foreign_key="acc_cash_account.id")
    note: str = Field(default="", max_length=300)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    order: Optional[PurchaseOrder] = Relationship(back_populates="payments")


# ============================================================
# TRẢ HÀNG CHO NCC (3 bước: DRAFT → APPROVED → CONFIRMED)
# ============================================================
class PurchaseReturn(SQLModel, table=True):
    __tablename__ = "purchase_return"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    supplier_id: int = Field(foreign_key="inv_supplier.id", index=True)
    original_order_id: Optional[int] = Field(default=None, foreign_key="purchase_order.id")
    user_id: Optional[int] = Field(default=None, index=True)

    status: str = Field(default="DRAFT", max_length=20)
    # DRAFT / APPROVED / CONFIRMED / CANCELLED

    total_amount: float = Field(default=0.0)
    refund_method: str = Field(default="CREDIT", max_length=20)  # CASH/BANK/CREDIT

    reason: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)

    # Chữ ký NCC
    signature_note: str = Field(default="", max_length=500)
    confirmed_at: Optional[datetime] = Field(default=None)

    # Email
    email_sent_at: Optional[datetime] = Field(default=None)
    email_sent_to: str = Field(default="", max_length=200)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    approved_at: Optional[datetime] = Field(default=None)

    lines: List["PurchaseReturnLine"] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PurchaseReturnLine(SQLModel, table=True):
    __tablename__ = "purchase_return_line"

    id: Optional[int] = Field(default=None, primary_key=True)
    return_id: int = Field(foreign_key="purchase_return.id", index=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)
    uom_id: Optional[int] = Field(default=None, foreign_key="inv_product_uom.id")

    # Lô nhập gốc để lấy đúng giá
    stock_layer_id: Optional[int] = Field(default=None, foreign_key="inv_stock_layer.id")

    quantity: int = Field(default=0)
    base_quantity: int = Field(default=0)
    unit_price: float = Field(default=0.0)   # Giá nhập của lô
    refund_amount: float = Field(default=0.0)

    reason: str = Field(default="", max_length=300)
    stock_move_id: Optional[int] = Field(default=None, foreign_key="inv_stock_move.id")