# app/modules/quan_ly_kho/router.py
from datetime import datetime
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import TEMPLATES_DIR
from app.core.database import get_session
from app.modules.quan_ly_kho import services
from app.modules.quan_ly_kho.schemas import (
    CategoryCreate, CategoryUpdate,
    SupplierCreate, SupplierUpdate,
    ProductCreate, ProductUpdate,
    ProductUoMCreate, BarcodeCreate, StockMoveCreateFull,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])
from app.core.templates import templates


# ============================================================
# HELPERS
# ============================================================
def _to_int_or_none(s):
    if s is None:
        return None
    if isinstance(s, int):
        return s
    s = str(s).strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _redirect_with_msg(url: str, kind: str, msg: str):
    """Redirect kèm thông báo (error= hoặc success=)."""
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# CATEGORY
# ============================================================
@router.post("/categories/create")
def category_create(name: str = Form(...), note: str = Form(""),
                    session: Session = Depends(get_session)):
    services.create_category(session, CategoryCreate(name=name, note=note))
    return RedirectResponse(url="/inventory/products", status_code=303)


@router.post("/categories/{cid}/update")
def category_update(cid: int, name: str = Form(...), note: str = Form(""),
                    session: Session = Depends(get_session)):
    services.update_category(session, cid, CategoryUpdate(name=name, note=note))
    return RedirectResponse(url="/inventory/categories", status_code=303)


@router.post("/categories/{cid}/delete")
def category_delete(cid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_category(session, cid)
    kind = "success" if ok else "error"
    return _redirect_with_msg("/inventory/categories", kind, msg)


@router.get("/categories")
def category_list(request: Request, session: Session = Depends(get_session)):
    cats = services.get_all_categories(session)
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/category_list.html",
        context={"categories": cats},
    )


# ============================================================
# SUPPLIER
# ============================================================
@router.get("/suppliers")
def supplier_list(request: Request, session: Session = Depends(get_session)):
    sups = services.get_all_suppliers(session)
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/supplier_list.html",
        context={"suppliers": sups},
    )


@router.get("/suppliers/new")
def supplier_new_form(request: Request):
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/supplier_form.html",
        context={"supplier": None, "is_edit": False},
    )


@router.get("/suppliers/{sid}/edit")
def supplier_edit_form(sid: int, request: Request,
                       session: Session = Depends(get_session)):
    sup = services.get_supplier(session, sid)
    if not sup:
        return RedirectResponse(url="/inventory/suppliers", status_code=303)
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/supplier_form.html",
        context={"supplier": sup, "is_edit": True},
    )


@router.post("/suppliers/create")
def supplier_create(
    code: str = Form(...), name: str = Form(...),
    phone: str = Form(""), email: str = Form(""),
    address: str = Form(""), tax_code: str = Form(""),
    note: str = Form(""),
    payment_term_days: int = Form(30),
    session: Session = Depends(get_session),
):
    services.create_supplier(session, SupplierCreate(
        code=code, name=name, phone=phone, email=email,
        address=address, tax_code=tax_code, note=note,
	payment_term_days=payment_term_days,
    ))
    return RedirectResponse(url="/inventory/suppliers", status_code=303)


@router.post("/suppliers/{sid}/update")
def supplier_update(
    sid: int,
    code: str = Form(...), name: str = Form(...),
    phone: str = Form(""), email: str = Form(""),
    address: str = Form(""), tax_code: str = Form(""),
    note: str = Form(""),
    payment_term_days: int = Form(30),
    session: Session = Depends(get_session),
):
    services.update_supplier(session, sid, SupplierUpdate(
        code=code, name=name, phone=phone, email=email,
        address=address, tax_code=tax_code, note=note,
        payment_term_days=payment_term_days,
    ))
    return RedirectResponse(url="/inventory/suppliers", status_code=303)


@router.post("/suppliers/{sid}/delete")
def supplier_delete(sid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_supplier(session, sid)
    kind = "success" if ok else "error"
    return _redirect_with_msg("/inventory/suppliers", kind, msg)

# ============================================================
# API JSON (cho JS gọi)
# ============================================================
@router.get("/api/products/{pid}/uoms")
def api_product_uoms(pid: int, session: Session = Depends(get_session)):
    uoms = services.get_uoms_of_product(session, pid)
    return {
        "uoms": [
            {"id": u.id, "name": u.name, "factor": u.factor, "sale_price": u.sale_price}
            for u in uoms
        ]
    }


# ============================================================
# PRODUCT
# ============================================================
@router.get("/products")
def product_list(request: Request, q: str = "",
                 session: Session = Depends(get_session)):
    products_data = services.search_products(session, keyword=q)
    categories = services.get_all_categories(session)
    suppliers = services.get_all_suppliers(session)

    products = []
    for prod, cat in products_data:
        margin = 0.0
        if prod.price > 0:
            margin = (prod.price - prod.cost_price) / prod.price * 100
        products.append({
            "id": prod.id, "sku": prod.sku, "name": prod.name,
            "unit": prod.unit, "price": prod.price,
            "cost_price": prod.cost_price,
            "stock_quantity": prod.stock_quantity,
            "min_stock": prod.min_stock,
            "tax_rate": prod.tax_rate,
            "cost_method": prod.cost_method,
            "category_name": cat.name if cat else "Chưa phân loại",
            "margin": margin,
            "low_stock": prod.stock_quantity <= prod.min_stock,
        })

    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/product_list.html",
        context={
            "products": products, "categories": categories,
            "suppliers": suppliers, "keyword": q,
        },
    )


@router.get("/products/new")
def product_new_form(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/product_form.html",
        context={
            "product": None, "is_edit": False,
            "categories": services.get_all_categories(session),
            "suppliers": services.get_all_suppliers(session),
        },
    )


@router.get("/products/{pid}/edit")
def product_edit_form(pid: int, request: Request,
                      session: Session = Depends(get_session)):
    product = services.get_product(session, pid)
    if not product:
        return RedirectResponse(url="/inventory/products", status_code=303)
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/product_form.html",
        context={
            "product": product, "is_edit": True,
            "categories": services.get_all_categories(session),
            "suppliers": services.get_all_suppliers(session),
        },
    )


@router.post("/products/create")
def product_create(
    sku: str = Form(...), name: str = Form(...),
    unit: str = Form("Cái"), price: float = Form(0.0),
    cost_price: float = Form(0.0),
    tax_rate: float = Form(0.0), min_stock: int = Form(0),
    cost_method: str = Form("FIFO"),
    category_id: str = Form(""), supplier_id: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        services.create_product(session, ProductCreate(
            sku=sku, name=name, unit=unit, price=price,
            cost_price=cost_price, tax_rate=tax_rate,
            min_stock=min_stock, cost_method=cost_method,
            category_id=_to_int_or_none(category_id),
            supplier_id=_to_int_or_none(supplier_id),
        ))
    except Exception as e:
        return _redirect_with_msg("/inventory/products", "error", str(e))
    return RedirectResponse(url="/inventory/products", status_code=303)


@router.post("/products/{pid}/update")
def product_update(
    pid: int,
    sku: str = Form(...), name: str = Form(...),
    unit: str = Form("Cái"), price: float = Form(0.0),
    cost_price: float = Form(0.0),
    tax_rate: float = Form(0.0), min_stock: int = Form(0),
    cost_method: str = Form("FIFO"),
    category_id: str = Form(""), supplier_id: str = Form(""),
    session: Session = Depends(get_session),
):
    services.update_product(session, pid, ProductUpdate(
        sku=sku, name=name, unit=unit, price=price,
        cost_price=cost_price, tax_rate=tax_rate,
        min_stock=min_stock, cost_method=cost_method,
        category_id=_to_int_or_none(category_id),
        supplier_id=_to_int_or_none(supplier_id),
    ))
    return RedirectResponse(url="/inventory/products", status_code=303)


@router.post("/products/{pid}/delete")
def product_delete(pid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_product(session, pid)
    kind = "success" if ok else "error"
    return _redirect_with_msg("/inventory/products", kind, msg)


@router.get("/products/{pid}")
def product_detail(pid: int, request: Request,
                   session: Session = Depends(get_session)):
    product = services.get_product(session, pid)
    if not product:
        return RedirectResponse(url="/inventory/products", status_code=303)

    cat = services.get_category(session, product.category_id) if product.category_id else None
    sup = services.get_supplier(session, product.supplier_id) if product.supplier_id else None

    uoms = services.get_uoms_of_product(session, pid)
    barcodes = services.get_barcodes_of_product(session, pid)
    moves = services.get_stock_moves(session, product_id=pid)

    margin = 0.0
    if product.price > 0:
        margin = (product.price - product.cost_price) / product.price * 100

    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/product_detail.html",
        context={
            "product": product, "category": cat, "supplier": sup,
            "uoms": uoms, "barcodes": barcodes, "moves": moves,
            "margin": margin,
        },
    )


# ============================================================
# UOM
# ============================================================
@router.post("/products/{pid}/uoms/create")
def uom_create(
    pid: int, name: str = Form(...), factor: int = Form(...),
    sale_price: float = Form(0.0),
    session: Session = Depends(get_session),
):
    if factor <= 0:
        return _redirect_with_msg(f"/inventory/products/{pid}", "error",
                                   "Hệ số quy đổi phải lớn hơn 0")
    services.create_uom(session, ProductUoMCreate(
        product_id=pid, name=name, factor=factor, sale_price=sale_price,
    ))
    return RedirectResponse(url=f"/inventory/products/{pid}", status_code=303)


@router.post("/uoms/{uid}/delete")
def uom_delete(uid: int, session: Session = Depends(get_session)):
    uom = session.get.__self__  # không dùng
    from app.modules.quan_ly_kho.models import ProductUoM
    u = session.get(ProductUoM, uid)
    pid = u.product_id if u else 0
    ok, msg = services.delete_uom(session, uid)
    kind = "success" if ok else "error"
    return _redirect_with_msg(f"/inventory/products/{pid}", kind, msg)


# ============================================================
# BARCODE
# ============================================================
@router.post("/products/{pid}/barcodes/create")
def barcode_create(
    pid: int, code: str = Form(...),
    uom_id: str = Form(""), note: str = Form(""),
    session: Session = Depends(get_session),
):
    b, msg = services.create_barcode(session, BarcodeCreate(
        code=code, product_id=pid,
        uom_id=_to_int_or_none(uom_id), note=note,
    ))
    kind = "success" if b else "error"
    return _redirect_with_msg(f"/inventory/products/{pid}", kind, msg)


@router.post("/barcodes/{bid}/delete")
def barcode_delete(bid: int, session: Session = Depends(get_session)):
    from app.modules.quan_ly_kho.models import Barcode
    b = session.get(Barcode, bid)
    pid = b.product_id if b else 0
    services.delete_barcode(session, bid)
    return RedirectResponse(url=f"/inventory/products/{pid}", status_code=303)


# ============================================================
# PRINT BARCODE
# ============================================================
@router.get("/products/{pid}/print-barcodes")
def print_barcodes(pid: int, request: Request,
                   session: Session = Depends(get_session)):
    product = services.get_product(session, pid)
    if not product:
        return RedirectResponse(url="/inventory/products", status_code=303)
    barcodes = services.get_barcodes_of_product(session, pid)
    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/print_barcode.html",
        context={"product": product, "barcodes": barcodes},
    )


# ============================================================
# STOCK MOVES
# ============================================================
@router.get("/stock-moves")
def stock_move_list(request: Request,
                    product_id: str = "",
                    session: Session = Depends(get_session)):
    pid = _to_int_or_none(product_id)
    moves = services.get_stock_moves(session, product_id=pid)
    products_data = services.get_all_products(session)
    product_dict = {p.id: f"{p.sku} - {p.name}" for p, _ in products_data}

    return templates.TemplateResponse(
        request=request, name="quan_ly_kho/stock_move_list.html",
        context={
            "moves": moves, "products": products_data,
            "product_dict": product_dict, "filter_pid": pid,
        },
    )


@router.post("/stock-moves/create")
def stock_move_create(
    product_id: int = Form(...),
    quantity: int = Form(...),
    unit_price: float = Form(0.0),
    move_type: str = Form(...),
    uom_id: str = Form(""),
    uom_quantity: int = Form(0),
    export_reason: str = Form(""),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        services.create_stock_move(session, StockMoveCreateFull(
            product_id=product_id, quantity=quantity,
            unit_price=unit_price, move_type=move_type,
            uom_id=_to_int_or_none(uom_id),
            uom_quantity=uom_quantity,
            export_reason=export_reason, note=note,
        ))
    except ValueError as e:
        return _redirect_with_msg("/inventory/stock-moves", "error", str(e))
    return RedirectResponse(url="/inventory/stock-moves", status_code=303)


@router.post("/stock-moves/{mid}/delete")
def stock_move_delete(mid: int, session: Session = Depends(get_session)):
    result = services.precheck_delete_move(session, mid)
    if not result.success:
        if result.need_force:
            return _redirect_with_msg(
                "/inventory/stock-moves", "error",
                f"{result.message} Dùng chức năng Force Delete để sửa."
            )
        return _redirect_with_msg("/inventory/stock-moves", "error", result.message)

    ok, msg = services.delete_move_simple(session, mid)
    kind = "success" if ok else "error"
    return _redirect_with_msg("/inventory/stock-moves", kind, msg)


@router.post("/stock-moves/{mid}/force-delete")
def stock_move_force_delete(mid: int, session: Session = Depends(get_session)):
    ok, msg = services.force_delete_move_with_replay(session, mid)
    kind = "success" if ok else "error"
    return _redirect_with_msg("/inventory/stock-moves", kind, msg)


@router.get("/stock-moves/export")
def stock_moves_export(product_id: str = "",
                       session: Session = Depends(get_session)):
    pid = _to_int_or_none(product_id)
    csv_content = services.export_moves_csv(session, product_id=pid)
    filename = f"stock_moves_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )