from typing import List
from sqlmodel import Session, select
from app.modules.quan_ly_kho.models import Category, Product
from app.modules.quan_ly_kho.schemas import CategoryCreate, ProductCreate

# --- Các hàm xử lý Category ---
def get_all_categories(session: Session) -> List[Category]:
    return list(session.exec(select(Category)).all())

def create_category(session: Session, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump())
    session.add(category)
    session.commit()
    session.refresh(category)
    return category

# --- Các hàm xử lý Product ---
def get_all_products(session: Session) -> List[Product]:
    # Lấy sản phẩm kèm theo thông tin danh mục (join)
    statement = select(Product, Category).join(Category, isouter=True)
    results = session.exec(statement).all()
    return results

def create_product(session: Session, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    session.add(product)
    session.commit()
    session.refresh(product)
    return product