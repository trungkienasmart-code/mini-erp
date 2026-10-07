# app/modules/ke_toan/schemas.py
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ HKD PROFILE ============
class HKDProfileCreate(BaseModel):
    business_name: str
    tax_code: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    hkd_group: int = 1
    vat_rate_retail: float = 1.0
    vat_rate_service: float = 5.0
    tncn_rate: float = 0.5
    has_other_taxes: bool = False
    opening_cash: float = 0.0
    opening_bank: float = 0.0
    fiscal_year_start: str = "01-01"
    shift_diff_threshold: float = 50000.0
    note: str = ""

class HKDProfileUpdate(HKDProfileCreate):
    pass


# ============ CASH ACCOUNT ============
class CashAccountCreate(BaseModel):
    code: str
    name: str
    account_type: str  # CASH / BANK
    bank_name: str = ""
    bank_account_no: str = ""
    bank_branch: str = ""
    opening_balance: float = 0.0
    note: str = ""

class CashAccountUpdate(CashAccountCreate):
    status: str = "ACTIVE"


# ============ VOUCHER ============
class VoucherCreate(BaseModel):
    voucher_type: str  # RECEIPT / PAYMENT
    cash_account_id: int
    partner_type: str = "OTHER"
    partner_id: Optional[int] = None
    partner_name: str = ""
    amount: float = Field(gt=0)
    category: str = ""
    reason: str = ""
    note: str = ""
    ref_type: str = ""
    ref_id: Optional[int] = None
    voucher_date: Optional[date] = None


# ============ FIXED ASSET ============
class FixedAssetCreate(BaseModel):
    code: str
    name: str
    asset_type: str = "TSCD"
    unit: str = "Cái"
    quantity: int = 1
    original_cost: float = 0.0
    depreciation_rate: float = 0.0
    purchase_date: Optional[date] = None
    start_use_date: Optional[date] = None
    location: str = ""
    note: str = ""

class FixedAssetUpdate(FixedAssetCreate):
    pass


class AssetDisposal(BaseModel):
    disposal_date: date
    disposal_reason: str = ""
    disposal_value: float = 0.0


# ============ PERIOD LOCK ============
class PeriodLockCreate(BaseModel):
    period: str  # YYYY-MM
    note: str = ""
