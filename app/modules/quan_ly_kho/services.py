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

from app.modules.quan_ly_kho.models import StockMove
from app.modules.quan_ly_kho.schemas import StockMoveCreate

def create_stock_move(session: Session, data: StockMoveCreate) -> StockMove:
    """Tạo phiếu nhập/xuất kho và cập nhật tồn kho."""
    product = session.get(Product, data.product_id)
    if not product:
        raise ValueError("Sản phẩm không tồn tại")
    
    if data.move_type == "IN":
        product.stock_quantity += data.quantity
    elif data.move_type == "OUT":
        if product.stock_quantity < data.quantity:
            raise ValueError("Số lượng tồn kho không đủ")
        product.stock_quantity -= data.quantity
    else:
        raise ValueError("Loại giao dịch không hợp lệ")
    
    move = StockMove(
        product_id=data.product_id,
        quantity=data.quantity,
        move_type=data.move_type,
        note=data.note
    )
    session.add(move)
    session.add(product)
    session.commit()
    session.refresh(move)
    return move

def get_stock_moves(session: Session) -> List[StockMove]:
    """Lấy toàn bộ lịch sử nhập/xuất, mới nhất lên đầu."""
    statement = select(StockMove).order_by(StockMove.created_at.desc())
    return list(session.exec(statement).all())

from app.modules.quan_ly_kho.schemas import ProductUpdate
from sqlmodel import or_

def get_product(session: Session, product_id: int) -> Product | None:
    return session.get(Product, product_id)

def update_product(session: Session, product_id: int, data: ProductUpdate) -> Product | None:
    product = session.get(Product, product_id)
    if not product:
        return None
    for key, value in data.model_dump().items():
        setattr(product, key, value)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product

def delete_product(session: Session, product_id: int) -> tuple[bool, str]:
    """Trả về (thành công, thông báo)."""
    from app.modules.quan_ly_kho.models import StockMove
    product = session.get(Product, product_id)
    if not product:
        return False, "Sản phẩm không tồn tại"
    # Kiểm tra có giao dịch kho không
    has_moves = session.exec(select(StockMove).where(StockMove.product_id == product_id)).first()
    if has_moves:
        return False, "Không thể xóa: Sản phẩm đã có giao dịch nhập/xuất"
    session.delete(product)
    session.commit()
    return True, "Đã xóa sản phẩm"

def search_products(session: Session, keyword: str = "") -> List:
    """Tìm kiếm theo SKU hoặc tên."""
    statement = select(Product, Category).join(Category, isouter=True)
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(or_(Product.sku.like(pattern), Product.name.like(pattern)))
    statement = statement.order_by(Product.sku)
    return session.exec(statement).all()