from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class Category(SQLModel, table=True):
    __tablename__ = "inv_category"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    
    # Quan hệ 1-N: Một danh mục có nhiều sản phẩm
    products: List["Product"] = Relationship(back_populates="category")

class Product(SQLModel, table=True):
    __tablename__ = "inv_product"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(max_length=50, index=True, unique=True) # Mã sản phẩm
    name: str = Field(max_length=200)
    unit: str = Field(default="Cái", max_length=20) # Đơn vị tính
    price: float = Field(default=0.0) # Giá bán
    stock_quantity: int = Field(default=0) # Tồn kho hiện tại
    
    # Khóa ngoại liên kết tới Category
    category_id: Optional[int] = Field(default=None, foreign_key="inv_category.id")
    category: Optional[Category] = Relationship(back_populates="products")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StockMove(SQLModel, table=True):
    __tablename__ = "inv_stock_move"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="inv_product.id")
    quantity: int = Field(default=0)  # Số lượng (luôn dương)
    move_type: str = Field(max_length=20)  # "IN" hoặc "OUT"
    note: str = Field(default="", max_length=255)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Quan hệ với Product
    product: Optional[Product] = Relationship()