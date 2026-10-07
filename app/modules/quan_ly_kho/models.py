# app/modules/quan_ly_kho/models.py
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# DANH MỤC
# ============================================================
class Category(SQLModel, table=True):
    __tablename__ = "inv_category"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    note: str = Field(default="", max_length=255)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    products: List["Product"] = Relationship(back_populates="category")


# ============================================================
# NHÀ CUNG CẤP
# ============================================================
class Supplier(SQLModel, table=True):
    __tablename__ = "inv_supplier"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=200)
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=300)
    tax_code: str = Field(default="", max_length=30)
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = Field(default="", max_length=500)
    payment_term_days: int = Field(default=30)   # Số ngày được nợ
    current_debt: float = Field(default=0.0)     # Công nợ hiện tại
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# SẢN PHẨM
# ============================================================
class Product(SQLModel, table=True):
    __tablename__ = "inv_product"

    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=200)
    unit: str = Field(default="Cái", max_length=20)

    price: float = Field(default=0.0)
    cost_price: float = Field(default=0.0)
    stock_quantity: int = Field(default=0)

    tax_rate: float = Field(default=0.0)
    min_stock: int = Field(default=0)
    cost_method: str = Field(default="FIFO", max_length=10)
    business_category: str = Field(default="RETAIL", max_length=30)
    # RETAIL (bán lẻ) / SERVICE (dịch vụ) / OTHER

    category_id: Optional[int] = Field(default=None, foreign_key="inv_category.id")
    supplier_id: Optional[int] = Field(default=None, foreign_key="inv_supplier.id")

    category: Optional[Category] = Relationship(back_populates="products")
    supplier: Optional[Supplier] = Relationship()

    barcodes: List["Barcode"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    uoms: List["ProductUoM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# ĐƠN VỊ BÁN HÀNG
# ============================================================
class ProductUoM(SQLModel, table=True):
    __tablename__ = "inv_product_uom"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)
    name: str = Field(max_length=50)
    factor: int = Field(default=1)
    sale_price: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    product: Optional[Product] = Relationship(back_populates="uoms")


# ============================================================
# MÃ VẠCH
# ============================================================
class Barcode(SQLModel, table=True):
    __tablename__ = "inv_barcode"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, index=True, unique=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)
    uom_id: Optional[int] = Field(default=None, foreign_key="inv_product_uom.id")
    note: str = Field(default="", max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    product: Optional[Product] = Relationship(back_populates="barcodes")


# ============================================================
# LÔ NHẬP
# ============================================================
class StockLayer(SQLModel, table=True):
    __tablename__ = "inv_stock_layer"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)
    stock_move_id: Optional[int] = Field(default=None, foreign_key="inv_stock_move.id")

    initial_qty: int = Field(default=0)
    remaining_qty: int = Field(default=0)
    unit_cost: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


# ============================================================
# PHIẾU NHẬP/XUẤT
# ============================================================
class StockMove(SQLModel, table=True):
    __tablename__ = "inv_stock_move"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="inv_product.id", index=True)

    quantity: int = Field(default=0)
    unit_price: float = Field(default=0.0)
    move_type: str = Field(max_length=20)

    uom_id: Optional[int] = Field(default=None, foreign_key="inv_product_uom.id")
    uom_quantity: int = Field(default=0)

    cost_price_at_move: float = Field(default=0.0)
    export_reason: str = Field(default="", max_length=30)
    note: str = Field(default="", max_length=255)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


# ============================================================
# LOG THAO TÁC
# ============================================================
class StockMoveLog(SQLModel, table=True):
    __tablename__ = "inv_stock_move_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = Field(max_length=50)
    stock_move_id: int = Field(index=True)
    detail: str = Field(default="", max_length=1000)
    replayed_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# LOG TIÊU THỤ LAYER
# ============================================================
class StockLayerConsumption(SQLModel, table=True):
    __tablename__ = "inv_stock_layer_consumption"

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_move_id: int = Field(foreign_key="inv_stock_move.id", index=True)
    layer_id: int = Field(foreign_key="inv_stock_layer.id", index=True)
    quantity: int = Field(default=0)
    unit_cost: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))