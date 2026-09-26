from pydantic import BaseModel

class CategoryCreate(BaseModel):
    name: str

class ProductCreate(BaseModel):
    sku: str
    name: str
    unit: str = "Cái"
    price: float = 0.0
    category_id: int | None = None