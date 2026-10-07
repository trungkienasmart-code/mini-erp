# app/modules/mua_hang/schemas.py
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ ORDER ============
class PurchaseOrderLineCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: int = Field(gt=0)
    unit_price: float = 0.0
    discount_percent: float = 0.0
    tax_rate: float = 0.0


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    payment_method: str = "DEBT"
    discount_amount: float = 0.0
    note: str = ""
    supplier_invoice_no: str = ""
    supplier_invoice_date: Optional[date] = None
    lines: List[PurchaseOrderLineCreate] = []


# ============ RECEIVE ============
class ReceiveLineInput(BaseModel):
    line_id: Optional[int] = None      # Nếu nhận theo đơn
    product_id: int
    uom_id: Optional[int] = None
    quantity: int = Field(gt=0)
    unit_price: float = 0.0
    tax_rate: float = 0.0


class ReceiveInput(BaseModel):
    order_id: Optional[int] = None     # Nhận theo đơn hay nhập nhanh
    supplier_id: Optional[int] = None
    supplier_invoice_no: str = ""
    supplier_invoice_date: Optional[date] = None
    note: str = ""
    lines: List[ReceiveLineInput] = []


# ============ PAYMENT ============
class PaymentCreate(BaseModel):
    order_id: int
    amount: float = Field(gt=0)
    payment_method: str = "CASH"
    cash_account_id: Optional[int] = None
    bank_transaction_code: str = ""
    note: str = ""


# ============ RETURN ============
class ReturnLineCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    stock_layer_id: Optional[int] = None
    quantity: int = Field(gt=0)
    unit_price: float = 0.0
    reason: str = ""


class ReturnCreate(BaseModel):
    supplier_id: int
    original_order_id: Optional[int] = None
    refund_method: str = "CREDIT"
    reason: str = ""
    note: str = ""
    lines: List[ReturnLineCreate] = []


class ReturnConfirm(BaseModel):
    signature_note: str = ""
    note: str = ""