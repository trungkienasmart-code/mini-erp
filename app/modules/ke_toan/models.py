# app/modules/ke_toan/models.py
from datetime import datetime, timezone, date
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# CẤU HÌNH HKD (HỘ KINH DOANH)
# ============================================================
class HKDProfile(SQLModel, table=True):
    __tablename__ = "acc_hkd_profile"

    id: Optional[int] = Field(default=None, primary_key=True)
    business_name: str = Field(max_length=200)
    tax_code: str = Field(default="", max_length=30)
    address: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=100)

    # Nhóm HKD theo TT152/2025/TT-BTC
    # 1: DT < 500tr, không GTGT, không TNCN
    # 2: DT >= 500tr, nộp GTGT+TNCN theo tỷ lệ % DT
    # 3: GTGT theo % DT + TNCN trên thu nhập tính thuế
    # 4: Có thuế khác (XNK, TTĐB, TN, BVMT...)
    hkd_group: int = Field(default=1)

    # Tỷ lệ % thuế (dùng cho nhóm 2, 3, 4)
    vat_rate_retail: float = Field(default=1.0)      # % GTGT bán lẻ
    vat_rate_service: float = Field(default=5.0)     # % GTGT dịch vụ
    tncn_rate: float = Field(default=0.5)            # % TNCN
    has_other_taxes: bool = Field(default=False)

    # Số dư đầu kỳ
    opening_cash: float = Field(default=0.0)
    opening_bank: float = Field(default=0.0)

    # Năm tài chính
    fiscal_year_start: str = Field(default="01-01", max_length=5)  # MM-DD
    shift_diff_threshold: float = Field(default=50000.0)  # Ngưỡng cảnh báo chênh lệch ca

    # Tháng đã khóa (JSON string các tháng "2026-01,2026-02")
    locked_months: str = Field(default="", max_length=500)

    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# TÀI KHOẢN QUỸ (TIỀN MẶT / NGÂN HÀNG)
# ============================================================
class CashAccount(SQLModel, table=True):
    __tablename__ = "acc_cash_account"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=200)
    account_type: str = Field(max_length=20)  # CASH / BANK

    bank_name: str = Field(default="", max_length=200)
    bank_account_no: str = Field(default="", max_length=50)
    bank_branch: str = Field(default="", max_length=200)

    opening_balance: float = Field(default=0.0)
    current_balance: float = Field(default=0.0)

    status: str = Field(default="ACTIVE", max_length=20)  # ACTIVE / INACTIVE
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    vouchers: List["Voucher"] = Relationship(back_populates="cash_account")


# ============================================================
# PHIẾU THU / PHIẾU CHI
# ============================================================
class Voucher(SQLModel, table=True):
    __tablename__ = "acc_voucher"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    voucher_type: str = Field(max_length=20)  # RECEIPT (thu) / PAYMENT (chi)

    cash_account_id: int = Field(foreign_key="acc_cash_account.id", index=True)

    partner_type: str = Field(default="OTHER", max_length=20)
    # CUSTOMER / SUPPLIER / EMPLOYEE / OTHER
    partner_id: Optional[int] = Field(default=None)
    partner_name: str = Field(default="", max_length=200)

    amount: float = Field(default=0.0)

    # Khoản mục chi phí theo TT152
    # CPCK: Chi phí chứng khoán
    # CPDVMN: Dịch vụ mua ngoài
    # CPKHTSCĐ: Khấu hao TSCĐ
    # CPLV: Chi phí lãi vay
    # CPNC: Chi phí nhân công
    # GVHB: Giá vốn hàng bán
    # KHAC: Khác
    category: str = Field(default="", max_length=50)

    reason: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)

    # Link chứng từ gốc
    ref_type: str = Field(default="", max_length=30)  # SALE / PURCHASE / OTHER
    ref_id: Optional[int] = Field(default=None)

    # Ngày chứng từ (có thể khác created_at)
    voucher_date: date = Field(default_factory=lambda: datetime.now(timezone.utc).date())

    user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    cash_account: Optional[CashAccount] = Relationship(back_populates="vouchers")


# ============================================================
# TÀI SẢN CỐ ĐỊNH / CÔNG CỤ DỤNG CỤ
# ============================================================
class FixedAsset(SQLModel, table=True):
    __tablename__ = "acc_fixed_asset"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=200)

    asset_type: str = Field(default="TSCD", max_length=20)  # TSCD / CCDC
    unit: str = Field(default="Cái", max_length=20)
    quantity: int = Field(default=1)

    original_cost: float = Field(default=0.0)
    depreciation_rate: float = Field(default=0.0)  # %/năm
    accumulated_depreciation: float = Field(default=0.0)

    purchase_date: Optional[date] = Field(default=None)
    start_use_date: Optional[date] = Field(default=None)
    location: str = Field(default="", max_length=200)  # Nơi sử dụng

    status: str = Field(default="ACTIVE", max_length=20)
    # ACTIVE / DISPOSED / LIQUIDATED

    disposal_date: Optional[date] = Field(default=None)
    disposal_reason: str = Field(default="", max_length=500)
    disposal_value: float = Field(default=0.0)

    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# KHẤU HAO TÀI SẢN
# ============================================================
class AssetDepreciation(SQLModel, table=True):
    __tablename__ = "acc_asset_depreciation"

    id: Optional[int] = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="acc_fixed_asset.id", index=True)

    period: str = Field(max_length=7)  # YYYY-MM
    depreciation_amount: float = Field(default=0.0)
    accumulated_before: float = Field(default=0.0)
    accumulated_after: float = Field(default=0.0)

    note: str = Field(default="", max_length=300)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# KHÓA KỲ KẾ TOÁN
# ============================================================
class PeriodLock(SQLModel, table=True):
    __tablename__ = "acc_period_lock"

    id: Optional[int] = Field(default=None, primary_key=True)
    period: str = Field(max_length=7, index=True, unique=True)  # YYYY-MM
    status: str = Field(default="OPEN", max_length=20)  # OPEN / CLOSED
    closed_at: Optional[datetime] = Field(default=None)
    closed_by: Optional[int] = Field(default=None)
    note: str = Field(default="", max_length=300)