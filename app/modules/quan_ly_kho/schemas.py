from pydantic import BaseModel

class CategoryCreate(BaseModel):
    name: str

class ProductCreate(BaseModel):
    sku: str
    name: str
    unit: str = "Cái"
    price: float = 0.0
    category_id: int | None = None

class StockMoveCreate(BaseModel):
    product_id: int
    quantity: int
    move_type: str  # "IN" hoặc "OUT"
    note: str = ""

class ProductUpdate(BaseModel):
    sku: str
    name: str
    unit: str = "Cái"
    price: float = 0.0
    cost_price: float = 0.0
    category_id: int | None = None