from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import TEMPLATES_DIR
from app.core.database import get_session
from app.modules.quan_ly_kho import services
from app.modules.quan_ly_kho.schemas import CategoryCreate, ProductCreate

router = APIRouter(prefix="/inventory", tags=["Inventory"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/products")
def product_list(request: Request, session: Session = Depends(get_session)):
    products_data = services.get_all_products(session)
    categories = services.get_all_categories(session)
    
    # Chuyển đổi dữ liệu trả về thành dạng dict để dễ hiển thị
    products = []
    for prod, cat in products_data:
        products.append({
            "id": prod.id,
            "sku": prod.sku,
            "name": prod.name,
            "unit": prod.unit,
            "price": prod.price,
            "stock_quantity": prod.stock_quantity,
            "category_name": cat.name if cat else "Chưa phân loại"
        })
        
    return templates.TemplateResponse(
        request=request,
        name="quan_ly_kho/product_list.html",
        context={"products": products, "categories": categories},
    )

@router.post("/products/create")
def product_create(
    sku: str = Form(...),
    name: str = Form(...),
    unit: str = Form("Cái"),
    price: float = Form(0.0),
    category_id: int | None = Form(None),
    session: Session = Depends(get_session),
):
    services.create_product(session, ProductCreate(sku=sku, name=name, unit=unit, price=price, category_id=category_id))
    return RedirectResponse(url="/inventory/products", status_code=303)

@router.post("/categories/create")
def category_create(
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    services.create_category(session, CategoryCreate(name=name))
    return RedirectResponse(url="/inventory/products", status_code=303)