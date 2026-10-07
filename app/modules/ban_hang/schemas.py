# app/modules/ban_hang/schemas.py
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ CUSTOMER ============
class CustomerCreate(BaseModel):
    code: str
    name: str
    phone: str = ""
    email: str = ""
    address: str = ""
    tax_code: str = ""
    customer_type: str = "RETAIL"
    credit_limit: float = 0.0
    note: str = ""

class CustomerUpdate(CustomerCreate):
    pass


# ============ DISCOUNT CODE ============
class DiscountCodeCreate(BaseModel):
    code: str
    name: str
    discount_type: str = "PERCENT"
    discount_value: float = 0.0
    max_discount: float = 0.0
    min_order_amount: float = 0.0
    apply_to: str = "ALL"
    category_id: Optional[int] = None
    product_id: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    max_uses: int = 0
    requires_approval: bool = False
    status: str = "ACTIVE"
    note: str = ""

class DiscountCodeUpdate(DiscountCodeCreate):
    pass


# ============ SHIFT ============
class ShiftOpen(BaseModel):
    opening_cash: float = 0.0
    user_id: Optional[int] = None
    note: str = ""

class ShiftDenominationInput(BaseModel):
    denomination: int
    quantity: int

class ShiftClose(BaseModel):
    denominations: List[ShiftDenominationInput] = []
    counted_cash: float = 0.0
    cash_account_id: Optional[int] = None
    bank_account_id: Optional[int] = None
    note: str = ""


# ============ SALE ORDER ============
class SaleOrderLineCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: int = Field(gt=0)
    unit_price: float = 0.0
    discount_percent: float = 0.0
    tax_rate: float = 0.0

class SaleOrderCreate(BaseModel):
    customer_id: Optional[int] = None
    order_type: str = "POS"  # POS / INVOICE
    payment_method: str = "CASH"
    discount_code_id: Optional[int] = None
    discount_amount: float = 0.0  # Giảm giá toàn đơn (nhập tay)
    note: str = ""
    lines: List[SaleOrderLineCreate] = []

    # VAT info
    want_vat_invoice: bool = False
    vat_company_name: str = ""
    vat_tax_code: str = ""
    vat_address: str = ""
    vat_email: str = ""

    # SĐT khách (POS nhanh)
    customer_phone: str = ""

    # Thanh toán (POS thường trả đủ ngay)
    paid_amount: float = 0.0
    customer_paid: float = 0.0  # Tiền khách đưa (cho bill in ra)


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
    quantity: int = Field(gt=0)
    unit_price: float = 0.0
    reason: str = ""

class ReturnCreate(BaseModel):
    original_order_id: Optional[int] = None
    customer_id: Optional[int] = None
    refund_method: str = "CASH"
    reason: str = ""
    note: str = ""
    lines: List[ReturnLineCreate] = []

class VatCustomerCreate(BaseModel):
    tax_code: str
    company_name: str
    address: str = ""
    email: str = ""
    phone: str = ""
    customer_id: Optional[int] = None