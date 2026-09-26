from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import TEMPLATES_DIR
from app.core.database import get_session
from app.modules.quan_ly_kho import services
from app.modules.quan_ly_kho.schemas import (
    CategoryCreate, ProductCreate, ProductUpdate, StockMoveCreate
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ============ DANH MỤC ============
@router.post("/categories/create")
def category_create(name: str = Form(...), session: Session = Depends(get_session)):
    services.create_category(session, CategoryCreate(name=name))
    return RedirectResponse(url="/inventory/products", status_code=303)

# ============ SẢN PHẨM ============
@router.get("/products")
def product_list(
    request: Request,
    q: str = "",
    session: Session = Depends(get_session),
):
    products_data = services.search_products(session, keyword=q)
    categories = services.get_all_categories(session)
    products = []
    for prod, cat in products_data:
        products.append({
            "id": prod.id, "sku": prod.sku, "name": prod.name,
            "unit": prod.unit, "price": prod.price,
            "cost_price": prod.cost_price,
            "stock_quantity": prod.stock_quantity,
            "category_name": cat.name if cat else "Chưa phân loại",
        })
    return templates.TemplateResponse(
        request=request,
        name="quan_ly_kho/product_list.html",
        context={"products": products, "categories": categories, "keyword": q},
    )

@router.get("/products/new")
def product_new_form(request: Request, session: Session = Depends(get_session)):
    categories = services.get_all_categories(session)
    return templates.TemplateResponse(
        request=request,
        name="quan_ly_kho/product_form.html",
        context={"product": None, "categories": categories, "is_edit": False},
    )

@router.get("/products/{product_id}/edit")
def product_edit_form(product_id: int, request: Request, session: Session = Depends(get_session)):
    product = services.get_product(session, product_id)
    if not product:
        return RedirectResponse(url="/inventory/products", status_code=303)
    categories = services.get_all_categories(session)
    return templates.TemplateResponse(
        request=request,
        name="quan_ly_kho/product_form.html",
        context={"product": product, "categories": categories, "is_edit": True},
    )

@router.post("/products/create")
def product_create(
    sku: str = Form(...), name: str = Form(...),
    unit: str = Form("Cái"), price: float = Form(0.0),
    cost_price: float = Form(0.0),
    category_id: int | None = Form(None),
    session: Session = Depends(get_session),
):
    services.create_product(session, ProductCreate(
        sku=sku, name=name, unit=unit, price=price,
        category_id=category_id
    ))
    return RedirectResponse(url="/inventory/products", status_code=303)

@router.post("/products/{product_id}/update")
def product_update(
    product_id: int,
    sku: str = Form(...), name: str = Form(...),
    unit: str = Form("Cái"), price: float = Form(0.0),
    cost_price: float = Form(0.0),
    category_id: int | None = Form(None),
    session: Session = Depends(get_session),
):
    services.update_product(session, product_id, ProductUpdate(
        sku=sku, name=name, unit=unit, price=price,
        cost_price=cost_price, category_id=category_id
    ))
    return RedirectResponse(url="/inventory/products", status_code=303)

@router.post("/products/{product_id}/delete")
def product_delete(product_id: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_product(session, product_id)
    if not ok:
        return RedirectResponse(url=f"/inventory/products?error={msg}", status_code=303)
    return RedirectResponse(url="/inventory/products", status_code=303)

# ============ NHẬP/XUẤT KHO ============
@router.get("/stock-moves")
def stock_move_list(request: Request, session: Session = Depends(get_session)):
    moves = services.get_stock_moves(session)
    products_data = services.get_all_products(session)
    product_dict = {p.id: f"{p.sku} - {p.name}" for p, _ in products_data}
    return templates.TemplateResponse(
        request=request,
        name="quan_ly_kho/stock_move_list.html",
        context={"moves": moves, "products": products_data, "product_dict": product_dict},
    )

@router.post("/stock-moves/create")
def stock_move_create(
    product_id: int = Form(...), quantity: int = Form(...),
    move_type: str = Form(...), note: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        services.create_stock_move(session, StockMoveCreate(
            product_id=product_id, quantity=quantity,
            move_type=move_type, note=note
        ))
    except ValueError as e:
        return RedirectResponse(url=f"/inventory/stock-moves?error={str(e)}", status_code=303)
    return RedirectResponse(url="/inventory/stock-moves", status_code=303)