# app/modules/quan_ly_kho/services.py
import csv
import io
from typing import List, Optional, Tuple

from sqlmodel import Session, select, or_

from app.modules.quan_ly_kho.models import (
    Category, Supplier, Product, ProductUoM, Barcode,
    StockLayer, StockMove, StockMoveLog, StockLayerConsumption,
)
from app.modules.quan_ly_kho.schemas import (
    CategoryCreate, CategoryUpdate,
    SupplierCreate, SupplierUpdate,
    ProductCreate, ProductUpdate,
    ProductUoMCreate,
    BarcodeCreate,
    StockMoveCreateFull,
    DeleteMoveResult,
)


# ============================================================
# CATEGORY
# ============================================================
def get_all_categories(session: Session) -> List[Category]:
    return list(session.exec(select(Category).order_by(Category.name)).all())

def get_category(session: Session, cid: int) -> Optional[Category]:
    return session.get(Category, cid)

def create_category(session: Session, data: CategoryCreate) -> Category:
    cat = Category(**data.model_dump())
    session.add(cat); session.commit(); session.refresh(cat)
    return cat

def update_category(session: Session, cid: int, data: CategoryUpdate) -> Optional[Category]:
    cat = session.get(Category, cid)
    if not cat:
        return None
    for k, v in data.model_dump().items():
        setattr(cat, k, v)
    session.add(cat); session.commit(); session.refresh(cat)
    return cat

def delete_category(session: Session, cid: int) -> Tuple[bool, str]:
    cat = session.get(Category, cid)
    if not cat:
        return False, "Danh mục không tồn tại"
    used = session.exec(select(Product).where(Product.category_id == cid)).first()
    if used:
        return False, "Không thể xóa: Có sản phẩm đang dùng danh mục này"
    session.delete(cat); session.commit()
    return True, "Đã xóa danh mục"


# ============================================================
# SUPPLIER
# ============================================================
def get_all_suppliers(session: Session) -> List[Supplier]:
    return list(session.exec(select(Supplier).order_by(Supplier.name)).all())

def get_supplier(session: Session, sid: int) -> Optional[Supplier]:
    return session.get(Supplier, sid)

def create_supplier(session: Session, data: SupplierCreate) -> Supplier:
    sup = Supplier(**data.model_dump())
    session.add(sup); session.commit(); session.refresh(sup)
    return sup

def update_supplier(session: Session, sid: int, data: SupplierUpdate) -> Optional[Supplier]:
    sup = session.get(Supplier, sid)
    if not sup:
        return None
    for k, v in data.model_dump().items():
        setattr(sup, k, v)
    session.add(sup); session.commit(); session.refresh(sup)
    return sup

def delete_supplier(session: Session, sid: int) -> Tuple[bool, str]:
    sup = session.get(Supplier, sid)
    if not sup:
        return False, "NCC không tồn tại"
    used = session.exec(select(Product).where(Product.supplier_id == sid)).first()
    if used:
        return False, "Không thể xóa: Có sản phẩm đang gắn NCC này"
    session.delete(sup); session.commit()
    return True, "Đã xóa NCC"


# ============================================================
# PRODUCT
# ============================================================
def search_products(session: Session, keyword: str = "") -> List:
    statement = select(Product, Category).join(Category, isouter=True)
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(Product.sku.like(pattern), Product.name.like(pattern))
        )
    statement = statement.order_by(Product.sku)
    return session.exec(statement).all()

def get_all_products(session: Session) -> List:
    """Lấy tất cả sản phẩm (dùng cho dropdown)."""
    return search_products(session, keyword="")

def get_product(session: Session, pid: int) -> Optional[Product]:
    return session.get(Product, pid)

def get_product_with_category(session: Session, pid: int):
    stmt = select(Product, Category).join(Category, isouter=True).where(Product.id == pid)
    return session.exec(stmt).first()

def create_product(session: Session, data: ProductCreate) -> Product:
    p = Product(**data.model_dump())
    session.add(p); session.commit(); session.refresh(p)
    return p

def update_product(session: Session, pid: int, data: ProductUpdate) -> Optional[Product]:
    p = session.get(Product, pid)
    if not p:
        return None
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    session.add(p); session.commit(); session.refresh(p)
    return p

def delete_product(session: Session, pid: int) -> Tuple[bool, str]:
    p = session.get(Product, pid)
    if not p:
        return False, "Sản phẩm không tồn tại"
    has_moves = session.exec(select(StockMove).where(StockMove.product_id == pid)).first()
    if has_moves:
        return False, "Không thể xóa: Sản phẩm đã có giao dịch nhập/xuất"
    session.delete(p); session.commit()
    return True, "Đã xóa sản phẩm"


# ============================================================
# PRODUCT UOM
# ============================================================
def get_uoms_of_product(session: Session, pid: int) -> List[ProductUoM]:
    return list(session.exec(
        select(ProductUoM).where(ProductUoM.product_id == pid)
    ).all())

def create_uom(session: Session, data: ProductUoMCreate) -> ProductUoM:
    u = ProductUoM(**data.model_dump())
    session.add(u); session.commit(); session.refresh(u)
    return u

def delete_uom(session: Session, uid: int) -> Tuple[bool, str]:
    u = session.get(ProductUoM, uid)
    if not u:
        return False, "Đơn vị không tồn tại"
    bc = session.exec(select(Barcode).where(Barcode.uom_id == uid)).first()
    if bc:
        return False, "Không thể xóa: Có mã vạch dùng đơn vị này"
    sm = session.exec(select(StockMove).where(StockMove.uom_id == uid)).first()
    if sm:
        return False, "Không thể xóa: Đã có giao dịch dùng đơn vị này"
    session.delete(u); session.commit()
    return True, "Đã xóa đơn vị"


# ============================================================
# BARCODE
# ============================================================
def get_barcodes_of_product(session: Session, pid: int) -> List[Barcode]:
    return list(session.exec(
        select(Barcode).where(Barcode.product_id == pid)
    ).all())

def get_barcode_by_code(session: Session, code: str) -> Optional[Barcode]:
    return session.exec(select(Barcode).where(Barcode.code == code)).first()

def create_barcode(session: Session, data: BarcodeCreate) -> Tuple[Optional[Barcode], str]:
    existing = get_barcode_by_code(session, data.code)
    if existing:
        return None, f"Mã vạch '{data.code}' đã tồn tại"
    b = Barcode(**data.model_dump())
    session.add(b); session.commit(); session.refresh(b)
    return b, "OK"

def delete_barcode(session: Session, bid: int) -> bool:
    b = session.get(Barcode, bid)
    if not b:
        return False
    session.delete(b); session.commit()
    return True


# ============================================================
# STOCK LAYER — CONSUME LOGIC (FIFO / LIFO)
# ============================================================
def _consume_layers_fifo(session: Session, product: Product, qty: int, move_id: int):
    layers = session.exec(
        select(StockLayer)
        .where(StockLayer.product_id == product.id)
        .where(StockLayer.remaining_qty > 0)
        .order_by(StockLayer.created_at.asc(), StockLayer.id.asc())
    ).all()
    return _consume_from_layers(session, layers, qty, move_id)

def _consume_layers_lifo(session: Session, product: Product, qty: int, move_id: int):
    layers = session.exec(
        select(StockLayer)
        .where(StockLayer.product_id == product.id)
        .where(StockLayer.remaining_qty > 0)
        .order_by(StockLayer.created_at.desc(), StockLayer.id.desc())
    ).all()
    return _consume_from_layers(session, layers, qty, move_id)

def _consume_from_layers(session: Session, layers: List[StockLayer], qty: int, move_id: int):
    """Tiêu thụ qty từ danh sách layers đã sắp xếp. Trả về giá vốn bình quân."""
    total_cost = 0.0
    total_qty = 0
    remaining = qty

    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.remaining_qty, remaining)
        if take <= 0:
            continue
        layer.remaining_qty -= take
        session.add(layer)

        total_cost += take * layer.unit_cost
        total_qty += take
        remaining -= take

        # Ghi log consumption
        cons = StockLayerConsumption(
            stock_move_id=move_id,
            layer_id=layer.id,
            quantity=take,
            unit_cost=layer.unit_cost,
        )
        session.add(cons)

    if remaining > 0:
        raise ValueError(f"Không đủ tồn kho. Còn thiếu {remaining}")

    avg_cost = total_cost / total_qty if total_qty > 0 else 0.0
    return avg_cost, None


# ============================================================
# STOCK MOVE — CREATE
# ============================================================
def create_stock_move(session: Session, data: StockMoveCreateFull) -> StockMove:
    """Tạo phiếu nhập/xuất, cập nhật tồn kho + layer + giá vốn."""
    product = session.get(Product, data.product_id)
    if not product:
        raise ValueError("Sản phẩm không tồn tại")

    if data.move_type not in ("IN", "OUT"):
        raise ValueError("Loại giao dịch không hợp lệ")

    # Tạo move trước để có ID
    move = StockMove(
        product_id=data.product_id,
        quantity=data.quantity,
        unit_price=data.unit_price,
        move_type=data.move_type,
        uom_id=data.uom_id,
        uom_quantity=data.uom_quantity,
        export_reason=data.export_reason,
        note=data.note,
    )
    session.add(move)
    session.flush()  # Lấy ID nhưng chưa commit

    if data.move_type == "IN":
        product.stock_quantity += data.quantity
        if data.unit_price > 0:
            product.cost_price = data.unit_price
        # Tạo layer mới
        layer = StockLayer(
            product_id=product.id,
            stock_move_id=move.id,
            initial_qty=data.quantity,
            remaining_qty=data.quantity,
            unit_cost=data.unit_price,
        )
        session.add(layer)
    else:  # OUT
        if product.stock_quantity < data.quantity:
            session.rollback()
            raise ValueError(
                f"Không đủ tồn kho. Hiện có {product.stock_quantity}, cần xuất {data.quantity}"
            )
        if product.cost_method == "LIFO":
            avg_cost, _ = _consume_layers_lifo(session, product, data.quantity, move.id)
        else:
            avg_cost, _ = _consume_layers_fifo(session, product, data.quantity, move.id)
        product.stock_quantity -= data.quantity
        move.cost_price_at_move = avg_cost
        session.add(move)

    session.add(product)
    session.commit()
    session.refresh(move)
    return move


def get_stock_moves(session: Session, product_id: Optional[int] = None) -> List[StockMove]:
    stmt = select(StockMove)
    if product_id:
        stmt = stmt.where(StockMove.product_id == product_id)
    stmt = stmt.order_by(StockMove.created_at.desc(), StockMove.id.desc())
    return list(session.exec(stmt).all())


# ============================================================
# DELETE MOVE — THUẬT TOÁN 3 CẤP
# ============================================================
def precheck_delete_move(session: Session, move_id: int) -> DeleteMoveResult:
    """Kiểm tra xem move có xóa được không. Trả về gợi ý cho UI."""
    move = session.get(StockMove, move_id)
    if not move:
        return DeleteMoveResult(success=False, message="Phiếu không tồn tại")

    if move.move_type == "OUT":
        return DeleteMoveResult(success=True, message="Có thể xóa trực tiếp")

    # IN: kiểm tra layer đã bị tiêu thụ chưa
    layer = session.exec(
        select(StockLayer).where(StockLayer.stock_move_id == move_id)
    ).first()

    if not layer or layer.remaining_qty == layer.initial_qty:
        return DeleteMoveResult(success=True, message="Có thể xóa trực tiếp")

    # Đã bị tiêu thụ → cần Force Delete
    affected = _find_affected_moves(session, move)
    return DeleteMoveResult(
        success=False,
        message=f"Lô này đã được dùng cho {len(affected)} phiếu xuất.",
        need_force=True,
        affected_moves=affected,
    )


def _find_affected_moves(session: Session, move: StockMove) -> List[int]:
    """Tìm các OUT move phụ thuộc vào layer của move IN này."""
    layer = session.exec(
        select(StockLayer).where(StockLayer.stock_move_id == move.id)
    ).first()
    if not layer:
        return []
    consumptions = session.exec(
        select(StockLayerConsumption).where(StockLayerConsumption.layer_id == layer.id)
    ).all()
    return list({c.stock_move_id for c in consumptions})


def delete_move_simple(session: Session, move_id: int) -> Tuple[bool, str]:
    """Cấp 1: Xóa phiếu an toàn. Chỉ thành công nếu không phá vỡ dữ liệu."""
    move = session.get(StockMove, move_id)
    if not move:
        return False, "Phiếu không tồn tại"

    product = session.get(Product, move.product_id)

    if move.move_type == "OUT":
        # Hoàn trả các layer đã tiêu thụ
        consumptions = session.exec(
            select(StockLayerConsumption).where(
                StockLayerConsumption.stock_move_id == move_id
            )
        ).all()
        for cons in consumptions:
            layer = session.get(StockLayer, cons.layer_id)
            if layer:
                layer.remaining_qty += cons.quantity
                session.add(layer)
            session.delete(cons)
        if product:
            product.stock_quantity += move.quantity
            session.add(product)
        session.delete(move)
        session.commit()
        return True, "Đã xóa phiếu xuất và hoàn trả tồn kho"

    # IN
    layer = session.exec(
        select(StockLayer).where(StockLayer.stock_move_id == move_id)
    ).first()

    if layer and layer.remaining_qty < layer.initial_qty:
        return False, "Lô này đã được sử dụng, cần Force Delete"

    if layer:
        session.delete(layer)
    if product:
        product.stock_quantity -= move.quantity
        session.add(product)
    session.delete(move)
    session.commit()
    return True, "Đã xóa phiếu nhập"


def force_delete_move_with_replay(session: Session, move_id: int) -> Tuple[bool, str]:
    """
    Cấp 3: Xóa phiếu và REPLAY tất cả các phiếu sau nó (cùng sản phẩm).
    Dùng khi lô nhập đã bị tiêu thụ nhưng cần sửa sai.
    """
    move = session.get(StockMove, move_id)
    if not move:
        return False, "Phiếu không tồn tại"

    product_id = move.product_id
    delete_time = move.created_at

    # 1. Lấy tất cả moves sau thời điểm này (cùng sản phẩm), TRỪ chính nó
    later_moves = session.exec(
        select(StockMove)
        .where(StockMove.product_id == product_id)
        .where(StockMove.created_at >= delete_time)
        .where(StockMove.id != move_id)
        .order_by(StockMove.created_at.asc(), StockMove.id.asc())
    ).all()

    # 2. Xóa tất cả layers + consumptions của product
    all_layers = session.exec(
        select(StockLayer).where(StockLayer.product_id == product_id)
    ).all()
    for lyr in all_layers:
        session.delete(lyr)

    all_cons = session.exec(
        select(StockLayerConsumption)
        .join(StockMove, StockLayerConsumption.stock_move_id == StockMove.id)
        .where(StockMove.product_id == product_id)
    ).all()
    for c in all_cons:
        session.delete(c)

    # 3. Xóa move gốc
    session.delete(move)
    session.flush()

    # 4. Reset tồn kho về 0
    product = session.get(Product, product_id)
    if not product:
        session.rollback()
        return False, "Sản phẩm không tồn tại"
    product.stock_quantity = 0
    session.add(product)
    session.flush()

    # 5. Replay
    replayed = 0
    try:
        for m in later_moves:
            if m.move_type == "IN":
                product.stock_quantity += m.quantity
                layer = StockLayer(
                    product_id=product_id,
                    stock_move_id=m.id,
                    initial_qty=m.quantity,
                    remaining_qty=m.quantity,
                    unit_cost=m.unit_price,
                )
                session.add(layer)
            else:  # OUT
                if product.stock_quantity < m.quantity:
                    raise ValueError(
                        f"Replay thất bại: Phiếu xuất #{m.id} "
                        f"({m.created_at.strftime('%d/%m/%Y %H:%M')}) cần {m.quantity} "
                        f"nhưng tồn kho chỉ còn {product.stock_quantity}. "
                        f"Hãy sửa hoặc xóa phiếu xuất đó trước."
                    )
                # Xóa consumptions cũ của move này
                old_cons = session.exec(
                    select(StockLayerConsumption).where(
                        StockLayerConsumption.stock_move_id == m.id
                    )
                ).all()
                for oc in old_cons:
                    session.delete(oc)
                session.flush()

                if product.cost_method == "LIFO":
                    avg_cost, _ = _consume_layers_lifo(session, product, m.quantity, m.id)
                else:
                    avg_cost, _ = _consume_layers_fifo(session, product, m.quantity, m.id)
                product.stock_quantity -= m.quantity
                m.cost_price_at_move = avg_cost
                session.add(m)
            session.add(product)
            replayed += 1

        # 6. Ghi log
        log = StockMoveLog(
            action="FORCE_DELETE",
            stock_move_id=move_id,
            detail=f"Đã xóa phiếu #{move_id} và replay {replayed} phiếu sau đó",
            replayed_count=replayed,
        )
        session.add(log)
        session.commit()
        return True, f"Đã xóa và tính lại {replayed} phiếu thành công"

    except ValueError as e:
        session.rollback()
        return False, str(e)
    except Exception as e:
        session.rollback()
        return False, f"Lỗi khi replay: {e}"


# ============================================================
# EXPORT CSV
# ============================================================
def export_moves_csv(session: Session, product_id: Optional[int] = None) -> str:
    """Trả về nội dung CSV của lịch sử nhập/xuất."""
    moves = get_stock_moves(session, product_id=product_id)

    product_dict = {}
    for p in session.exec(select(Product)).all():
        product_dict[p.id] = f"{p.sku} - {p.name}"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Ngày", "Sản phẩm", "Loại", "Lý do xuất",
        "Số lượng", "Đơn giá", "Thành tiền", "Giá vốn", "Ghi chú"
    ])

    for m in moves:
        writer.writerow([
            m.id,
            m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            product_dict.get(m.product_id, "N/A"),
            "Nhập" if m.move_type == "IN" else "Xuất",
            m.export_reason or "",
            m.quantity,
            f"{m.unit_price:.0f}",
            f"{m.unit_price * m.quantity:.0f}",
            f"{m.cost_price_at_move:.0f}" if m.move_type == "OUT" else "",
            m.note,
        ])

    # Thêm BOM để Excel đọc đúng tiếng Việt
    return "\ufeff" + output.getvalue()