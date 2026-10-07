# app/modules/quan_ly_kho/schemas.py
from typing import Optional  # ← thêm vào đầu file
from datetime import datetime
from pydantic import BaseModel, Field


# ============ CATEGORY ============
class CategoryCreate(BaseModel):
    name: str
    note: str = ""

class CategoryUpdate(BaseModel):
    name: str
    note: str = ""


# ============ SUPPLIER ============
class SupplierCreate(BaseModel):
    code: str
    name: str
    phone: str = ""
    email: str = ""
    address: str = ""
    tax_code: str = ""
    note: str = ""
    payment_term_days: int = 30   # ← THÊM DÒNG NÀY

class SupplierUpdate(SupplierCreate):
    pass


# ============ PRODUCT ============
class ProductCreate(BaseModel):
    sku: str
    name: str
    unit: str = "Cái"
    price: float = 0.0
    cost_price: float = 0.0
    tax_rate: float = 0.0
    min_stock: int = 0
    cost_method: str = "FIFO"
    business_category: str = "RETAIL"  # ← THÊM DÒNG NÀY
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None

class ProductUpdate(ProductCreate):
    pass

class ProductRead(BaseModel):
    id: int
    sku: str
    name: str
    unit: str
    price: float
    cost_price: float
    stock_quantity: int
    tax_rate: float
    min_stock: int
    cost_method: str
    business_category: str  # ← THÊM DÒNG NÀY
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ PRODUCT UOM ============
class ProductUoMCreate(BaseModel):
    product_id: int
    name: str
    factor: int = Field(gt=0)  # Phải > 0
    sale_price: float = 0.0


# ============ BARCODE ============
class BarcodeCreate(BaseModel):
    code: str
    product_id: int
    uom_id: Optional[int] = None
    note: str = ""


# ============ STOCK MOVE ============
class StockMoveCreateFull(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: float = 0.0
    move_type: str  # "IN" hoặc "OUT"
    uom_id: Optional[int] = None
    uom_quantity: int = 0
    export_reason: str = ""   # Chỉ dùng cho OUT
    note: str = ""


# ============ KẾT QUẢ XÓA PHIẾU ============
class DeleteMoveResult(BaseModel):
    success: bool
    message: str
    need_force: bool = False        # True nếu cần Force Delete
    affected_moves: list[int] = []  # Danh sách các move bị ảnh hưởng (nếu có)