# app/modules/mua_hang/router.py
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from sqlmodel import Session

from app.core.templates import templates
from app.core.database import get_session
from app.modules.mua_hang import services
from app.modules.mua_hang.schemas import (
    PurchaseOrderCreate, PurchaseOrderLineCreate,
    ReceiveInput, ReceiveLineInput,
    PaymentCreate, ReturnCreate,
)
from app.modules.quan_ly_kho import services as kho_services
from app.modules.quan_ly_kho.models import Product

router = APIRouter(prefix="/purchase", tags=["Purchase"])


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


def _to_float(s, default=0.0):
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# DASHBOARD MUA HÀNG
# ============================================================
@router.get("/")
def purchase_home(request: Request, session: Session = Depends(get_session)):
    total_debt = sum(s.current_debt for s in services.get_all_suppliers(session))
    recent_orders = services.get_all_orders(session, limit=5)
    pending_count = len(services.get_all_orders(session, status="DRAFT", limit=500))

    # Đơn quá hạn
    today = datetime.now(timezone.utc).date()
    overdue = []
    for o in services.get_all_orders(session, limit=500):
        if o.due_date and o.due_date < today and o.status in ("RECEIVED", "PARTIAL"):
            overdue.append(o)

    supplier_dict = {s.id: s.name for s in services.get_all_suppliers(session)}

    return templates.TemplateResponse(
        request=request, name="mua_hang/home.html",
        context={
            "total_debt": total_debt,
            "recent_orders": recent_orders,
            "pending_count": pending_count,
            "overdue": overdue,
            "supplier_dict": supplier_dict,
        },
    )


# ============================================================
# API LOOKUP
# ============================================================
@router.get("/api/search-product")
def api_search_product(
    q: str = "",
    supplier_id: str = "",
    category_id: str = "",
    session: Session = Depends(get_session),
):
    """Tìm SP theo tên/SKU/NCC/danh mục, kèm barcode + doanh số 30 ngày."""
    from sqlmodel import select as sel, func as fn
    from app.modules.quan_ly_kho.models import Barcode
    from app.modules.ban_hang.models import SaleOrder, SaleOrderLine
    from datetime import timedelta

    sup_id = _to_int_or_none(supplier_id)
    cat_id = _to_int_or_none(category_id)

    # Query có filter
    products_data = kho_services.search_products(session, keyword=q)

    # Doanh số bán 30 ngày gần nhất
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    results = []
    for p, cat in products_data[:50]:
        # Filter theo NCC
        if sup_id and p.supplier_id != sup_id:
            continue
        if cat_id and p.category_id != cat_id:
            continue

        # Lấy barcode đầu tiên (nếu có)
        bc = session.exec(
            sel(Barcode).where(Barcode.product_id == p.id)
        ).first()

        # Doanh số bán 30 ngày
        sales_qty = session.exec(
            sel(fn.coalesce(fn.sum(SaleOrderLine.base_quantity), 0))
            .join(SaleOrder, SaleOrderLine.order_id == SaleOrder.id)
            .where(SaleOrderLine.product_id == p.id)
            .where(SaleOrder.created_at >= thirty_days_ago)
            .where(SaleOrder.status.in_(["PAID", "PARTIAL", "CONFIRMED"]))
        ).one() or 0

        results.append({
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "unit": p.unit,
            "cost_price": p.cost_price,
            "price": p.price,
            "tax_rate": p.tax_rate,
            "stock": p.stock_quantity,
            "supplier_id": p.supplier_id,
            "barcode": bc.code if bc else "",
            "sales_30d": int(sales_qty),
        })

    return JSONResponse({"products": results})


@router.get("/api/supplier/{sid}/products")
def api_supplier_products(
    sid: int, session: Session = Depends(get_session),
):
    """Lấy TẤT CẢ sản phẩm của NCC (dùng khi chọn NCC trong form đơn)."""
    from sqlmodel import select as sel
    from app.modules.quan_ly_kho.models import Barcode

    prods = session.exec(
        sel(Product).where(Product.supplier_id == sid).order_by(Product.name)
    ).all()

    results = []
    for p in prods:
        bc = session.exec(
            sel(Barcode).where(Barcode.product_id == p.id)
        ).first()
        results.append({
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "unit": p.unit,
            "cost_price": p.cost_price,
            "price": p.price,
            "tax_rate": p.tax_rate,
            "stock": p.stock_quantity,
            "barcode": bc.code if bc else "",
        })
    return JSONResponse({"products": results})


@router.get("/api/products/{pid}/uoms")
def api_product_uoms(pid: int, session: Session = Depends(get_session)):
    uoms = kho_services.get_uoms_of_product(session, pid)
    return JSONResponse({
        "uoms": [
            {"id": u.id, "name": u.name, "factor": u.factor, "sale_price": u.sale_price}
            for u in uoms
        ]
    })
@router.get("/api/supplier/{sid}/pending-orders")
def api_supplier_pending_orders(sid: int, session: Session = Depends(get_session)):
    """Lấy các đơn APPROVED của NCC chưa nhập kho."""
    from sqlmodel import select as sel, func as fn
    from app.modules.mua_hang.models import PurchaseOrder, PurchaseOrderLine

    orders = session.exec(
        sel(PurchaseOrder)
        .where(PurchaseOrder.supplier_id == sid)
        .where(PurchaseOrder.status == "APPROVED")
        .order_by(PurchaseOrder.created_at.desc())
    ).all()

    result = []
    for o in orders:
        count = session.exec(
            sel(fn.count()).select_from(PurchaseOrderLine)
            .where(PurchaseOrderLine.order_id == o.id)
        ).one() or 0
        result.append({
            "id": o.id,
            "code": o.code,
            "created_at": o.created_at.strftime("%d/%m/%Y %H:%M"),
            "total_amount": o.total_amount,
            "line_count": count,
        })
    return JSONResponse({"orders": result})


@router.get("/api/order/{oid}/lines")
def api_order_lines(oid: int, session: Session = Depends(get_session)):
    """Lấy dòng hàng của đơn để load vào form nhập."""
    order = services.get_order(session, oid)
    if not order:
        return JSONResponse({"found": False})

    lines = services.get_order_lines(session, oid)
    result = []
    for l in lines:
        p = session.get(Product, l.product_id)
        result.append({
            "line_id": l.id,
            "product_id": l.product_id,
            "sku": p.sku if p else "",
            "name": p.name if p else "",
            "unit": p.unit if p else "",
            "uom_id": l.uom_id,
            "quantity": l.quantity,
            "unit_price": l.unit_price,
            "tax_rate": l.tax_rate,
            "stock": p.stock_quantity if p else 0,
            "barcode": "",
        })
    return JSONResponse({
        "found": True,
        "order_id": order.id,
        "order_code": order.code,
        "supplier_id": order.supplier_id,
        "lines": result,
    })

@router.get("/api/lookup-barcode")
def api_lookup_barcode(code: str, session: Session = Depends(get_session)):
    from app.modules.quan_ly_kho.models import Barcode
    from sqlmodel import select
    bc = session.exec(select(Barcode).where(Barcode.code == code)).first()
    if not bc:
        return JSONResponse({"found": False})

    p = session.get(Product, bc.product_id)
    if not p:
        return JSONResponse({"found": False})

    return JSONResponse({
        "found": True,
        "product_id": p.id,
        "sku": p.sku,
        "name": p.name,
        "unit": p.unit,
        "cost_price": p.cost_price,
        "tax_rate": p.tax_rate,
    })


@router.get("/api/supplier/{sid}/stock-layers/{pid}")
def api_supplier_stock_layers(
    sid: int, pid: int, session: Session = Depends(get_session),
):
    """Lấy các lô nhập còn hàng của SP từ NCC này (cho form trả hàng)."""
    layers = services.get_stock_layers_by_product_and_supplier(session, pid, sid)
    return JSONResponse({
        "layers": [
            {
                "id": l["id"],
                "initial_qty": l["initial_qty"],
                "remaining_qty": l["remaining_qty"],
                "unit_cost": l["unit_cost"],
                "created_at": l["created_at"].strftime("%d/%m/%Y %H:%M"),
            }
            for l in layers
        ]
    })


# ============================================================
# ORDERS
# ============================================================
@router.get("/orders")
def order_list(
    request: Request, q: str = "", status: str = "",
    supplier_id: str = "",
    session: Session = Depends(get_session),
):
    orders = services.get_all_orders(
        session, keyword=q, status=status,
        supplier_id=_to_int_or_none(supplier_id),
    )
    suppliers = services.get_all_suppliers(session)
    supplier_dict = {s.id: s.name for s in suppliers}
    return templates.TemplateResponse(
        request=request, name="mua_hang/order_list.html",
        context={
            "orders": orders, "keyword": q, "status": status,
            "suppliers": suppliers, "supplier_dict": supplier_dict,
            "filter_sid": _to_int_or_none(supplier_id),
        },
    )


@router.get("/orders/new")
def order_new_form(request: Request, session: Session = Depends(get_session)):
    suppliers = services.get_all_suppliers(session)
    products_data = kho_services.search_products(session, keyword="")
    products = []
    for p, cat in products_data[:100]:
        products.append({
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "cost_price": p.cost_price,
            "tax_rate": p.tax_rate, "stock": p.stock_quantity,
            "supplier_id": p.supplier_id,
        })
    return templates.TemplateResponse(
        request=request, name="mua_hang/order_form.html",
        context={"suppliers": suppliers, "products": products, "order": None},
    )


@router.post("/orders/create")
async def order_create(request: Request, session: Session = Depends(get_session)):
    body = await request.json()
    try:
        lines = []
        for item in body.get("lines", []):
            lines.append(PurchaseOrderLineCreate(
                product_id=int(item["product_id"]),
                uom_id=_to_int_or_none(item.get("uom_id")),
                quantity=int(item["quantity"]),
                unit_price=_to_float(item.get("unit_price")),
                discount_percent=_to_float(item.get("discount_percent")),
                tax_rate=_to_float(item.get("tax_rate")),
            ))

        inv_date = None
        if body.get("supplier_invoice_date"):
            try:
                inv_date = datetime.strptime(
                    body["supplier_invoice_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                inv_date = None

        data = PurchaseOrderCreate(
            supplier_id=int(body["supplier_id"]),
            payment_method=body.get("payment_method", "DEBT"),
            discount_amount=_to_float(body.get("discount_amount", 0)),
            note=body.get("note", ""),
            supplier_invoice_no=body.get("supplier_invoice_no", ""),
            supplier_invoice_date=inv_date,
            lines=lines,
        )
        order, msg = services.create_purchase_order(session, data)
        if not order:
            return JSONResponse({"success": False, "message": msg}, status_code=400)
        return JSONResponse({
            "success": True,
            "order_id": order.id,
            "order_code": order.code,
            "redirect_url": f"/purchase/orders/{order.id}",
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)

# ============================================================
# EXPORT CSV
# ============================================================
@router.get("/orders/export")
def orders_export(status: str = "", session: Session = Depends(get_session)):
    csv_content = services.export_orders_csv(session, status=status)
    filename = f"purchase_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/receives/export")
def receives_export(session: Session = Depends(get_session)):
    csv_content = services.export_receives_csv(session)
    filename = f"purchase_receives_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/orders/{oid}")
def order_detail(
    oid: int, request: Request, session: Session = Depends(get_session),
):
    order = services.get_order(session, oid)
    if not order:
        return RedirectResponse(url="/purchase/orders", status_code=303)

    lines = services.get_order_lines(session, oid)
    payments = services.get_order_payments(session, oid)
    supplier = services.get_supplier(session, order.supplier_id)

    product_dict = {}
    for l in lines:
        p = session.get(Product, l.product_id)
        if p:
            product_dict[l.product_id] = p

    # Lấy danh sách tài khoản quỹ
    from app.modules.ke_toan.services import get_all_cash_accounts
    cash_accounts = get_all_cash_accounts(session, only_active=True)

    return templates.TemplateResponse(
        request=request, name="mua_hang/order_detail.html",
        context={
            "order": order, "lines": lines, "payments": payments,
            "supplier": supplier, "product_dict": product_dict,
            "cash_accounts": cash_accounts,
        },
    )


@router.post("/orders/{oid}/approve")
def order_approve(oid: int, session: Session = Depends(get_session)):
    ok, msg = services.approve_order(session, oid)
    return _redirect_with_msg(
        f"/purchase/orders/{oid}",
        "success" if ok else "error", msg,
    )


@router.post("/orders/{oid}/email-sent")
def order_email_sent(
    oid: int, email_to: str = Form(""),
    session: Session = Depends(get_session),
):
    ok, msg = services.mark_email_sent(session, oid, email_to)
    return _redirect_with_msg(
        f"/purchase/orders/{oid}",
        "success" if ok else "error", msg,
    )


@router.post("/orders/{oid}/cancel")
def order_cancel(oid: int, session: Session = Depends(get_session)):
    ok, msg = services.cancel_order(session, oid)
    return _redirect_with_msg(
        f"/purchase/orders/{oid}",
        "success" if ok else "error", msg,
    )


@router.post("/orders/{oid}/payment")
def order_payment(
    oid: int,
    amount: float = Form(...),
    payment_method: str = Form("CASH"),
    cash_account_id: str = Form(""),
    bank_transaction_code: str = Form(""),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    from app.modules.mua_hang.schemas import PaymentCreate
    ok, msg = services.add_payment(session, PaymentCreate(
        order_id=oid, amount=amount, payment_method=payment_method,
        cash_account_id=_to_int_or_none(cash_account_id),
        bank_transaction_code=bank_transaction_code, note=note,
    ))
    return _redirect_with_msg(
        f"/purchase/orders/{oid}",
        "success" if ok else "error", msg,
    )

# ============================================================
# RECEIVE — NHẬN HÀNG
# ============================================================
@router.get("/receives")
def receive_list(
    request: Request, q: str = "",
    session: Session = Depends(get_session),
):
    # Danh sách đơn đã nhận
    orders = session.exec(
        __import__('sqlmodel').select(
            __import__('app.modules.mua_hang.models', fromlist=['PurchaseOrder']).PurchaseOrder
        )
        .where(__import__('app.modules.mua_hang.models', fromlist=['PurchaseOrder']).PurchaseOrder.status.in_(
            ["RECEIVED", "PAID", "PARTIAL"]
        ))
        .order_by(__import__('app.modules.mua_hang.models', fromlist=['PurchaseOrder']).PurchaseOrder.created_at.desc())
        .limit(200)
    ).all()

    supplier_dict = {s.id: s.name for s in services.get_all_suppliers(session)}

    return templates.TemplateResponse(
        request=request, name="mua_hang/receive_list.html",
        context={
            "orders": orders, "supplier_dict": supplier_dict,
            "keyword": q,
        },
    )


@router.get("/receives/new")
def receive_new_form(
    request: Request, order_id: str = "",
    session: Session = Depends(get_session),
):
    """Form nhận hàng. Nếu có order_id → nhận theo đơn, ngược lại nhập nhanh."""
    suppliers = services.get_all_suppliers(session)
    products_data = kho_services.search_products(session, keyword="")
    products = []
    for p, cat in products_data[:100]:
        products.append({
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "cost_price": p.cost_price,
            "tax_rate": p.tax_rate, "stock": p.stock_quantity,
            "supplier_id": p.supplier_id,
        })

    order = None
    order_lines = []
    oid = _to_int_or_none(order_id)
    if oid:
        order = services.get_order(session, oid)
        if order:
            for l in services.get_order_lines(session, oid):
                p = session.get(Product, l.product_id)
                order_lines.append({
                    "line_id": l.id,
                    "product_id": l.product_id,
                    "sku": p.sku if p else "",
                    "name": p.name if p else "",
                    "unit": p.unit if p else "",
                    "uom_id": l.uom_id,
                    "quantity": l.quantity,
                    "unit_price": l.unit_price,
                    "tax_rate": l.tax_rate,
                })
    order = None
    order_lines = []
    supplier = None
    oid = _to_int_or_none(order_id)
    if oid:
        order = services.get_order(session, oid)
        if order:
            supplier = services.get_supplier(session, order.supplier_id)
            for l in services.get_order_lines(session, oid):
                p = session.get(Product, l.product_id)
                order_lines.append({
                    "line_id": l.id,
                    "product_id": l.product_id,
                    "sku": p.sku if p else "",
                    "name": p.name if p else "",
                    "unit": p.unit if p else "",
                    "uom_id": l.uom_id,
                    "quantity": l.quantity,
                    "unit_price": l.unit_price,
                    "tax_rate": l.tax_rate,
                })

    return templates.TemplateResponse(
        request=request, name="mua_hang/receive_form.html",
        context={
            "suppliers": suppliers, "products": products,
            "order": order, "order_lines": order_lines,
            "supplier": supplier,
        },
    )

    return templates.TemplateResponse(
        request=request, name="mua_hang/receive_form.html",
        context={
            "suppliers": suppliers, "products": products,
            "order": order, "order_lines": order_lines,
        },
    )


@router.post("/receives/create")
async def receive_create(request: Request, session: Session = Depends(get_session)):
    body = await request.json()
    try:
        lines = []
        for item in body.get("lines", []):
            lines.append(ReceiveLineInput(
                line_id=_to_int_or_none(item.get("line_id")),
                product_id=int(item["product_id"]),
                uom_id=_to_int_or_none(item.get("uom_id")),
                quantity=int(item["quantity"]),
                unit_price=_to_float(item.get("unit_price")),
                tax_rate=_to_float(item.get("tax_rate")),
            ))

        inv_date = None
        if body.get("supplier_invoice_date"):
            try:
                inv_date = datetime.strptime(
                    body["supplier_invoice_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                inv_date = None

        data = ReceiveInput(
            order_id=_to_int_or_none(body.get("order_id")),
            supplier_id=_to_int_or_none(body.get("supplier_id")),
            supplier_invoice_no=body.get("supplier_invoice_no", ""),
            supplier_invoice_date=inv_date,
            note=body.get("note", ""),
            lines=lines,
        )
        order, msg = services.receive_order(session, data)
        if not order:
            return JSONResponse({"success": False, "message": msg}, status_code=400)
        return JSONResponse({
            "success": True,
            "order_id": order.id,
            "order_code": order.code,
            "redirect_url": f"/purchase/orders/{order.id}",
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)


# ============================================================
# RETURNS
# ============================================================
@router.get("/returns")
def return_list(
    request: Request, q: str = "", status: str = "",
    session: Session = Depends(get_session),
):
    returns = services.get_all_returns(session, keyword=q, status=status)
    supplier_dict = {s.id: s.name for s in services.get_all_suppliers(session)}
    return templates.TemplateResponse(
        request=request, name="mua_hang/return_list.html",
        context={
            "returns": returns, "supplier_dict": supplier_dict,
            "keyword": q, "status": status,
        },
    )


@router.get("/returns/new")
def return_new_form(
    request: Request, order_id: str = "",
    session: Session = Depends(get_session),
):
    suppliers = services.get_all_suppliers(session)
    products_data = kho_services.search_products(session, keyword="")
    products = []
    for p, cat in products_data[:100]:
        products.append({
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "cost_price": p.cost_price,
            "supplier_id": p.supplier_id,
        })
    return templates.TemplateResponse(
        request=request, name="mua_hang/return_form.html",
        context={
            "suppliers": suppliers, "products": products,
            "original_order_id": _to_int_or_none(order_id),
        },
    )


@router.post("/returns/create")
async def return_create(request: Request, session: Session = Depends(get_session)):
    body = await request.json()
    try:
        from app.modules.mua_hang.schemas import ReturnLineCreate
        lines = []
        for item in body.get("lines", []):
            lines.append(ReturnLineCreate(
                product_id=int(item["product_id"]),
                uom_id=_to_int_or_none(item.get("uom_id")),
                stock_layer_id=_to_int_or_none(item.get("stock_layer_id")),
                quantity=int(item["quantity"]),
                unit_price=_to_float(item.get("unit_price")),
                reason=item.get("reason", ""),
            ))

        data = ReturnCreate(
            supplier_id=int(body["supplier_id"]),
            original_order_id=_to_int_or_none(body.get("original_order_id")),
            refund_method=body.get("refund_method", "CREDIT"),
            reason=body.get("reason", ""),
            note=body.get("note", ""),
            lines=lines,
        )
        ret, msg = services.create_return(session, data)
        if not ret:
            return JSONResponse({"success": False, "message": msg}, status_code=400)
        return JSONResponse({
            "success": True,
            "return_id": ret.id,
            "return_code": ret.code,
            "redirect_url": f"/purchase/returns/{ret.id}",
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)


@router.get("/returns/{rid}")
def return_detail(
    rid: int, request: Request, session: Session = Depends(get_session),
):
    ret = services.get_return(session, rid)
    if not ret:
        return RedirectResponse(url="/purchase/returns", status_code=303)

    lines = services.get_return_lines(session, rid)
    supplier = services.get_supplier(session, ret.supplier_id)

    product_dict = {}
    for l in lines:
        p = session.get(Product, l.product_id)
        if p:
            product_dict[l.product_id] = f"{p.sku} - {p.name}"

    return templates.TemplateResponse(
        request=request, name="mua_hang/return_detail.html",
        context={
            "ret": ret, "lines": lines, "supplier": supplier,
            "product_dict": product_dict,
        },
    )


@router.post("/returns/{rid}/approve")
def return_approve(rid: int, session: Session = Depends(get_session)):
    ok, msg = services.approve_return(session, rid)
    return _redirect_with_msg(
        f"/purchase/returns/{rid}",
        "success" if ok else "error", msg,
    )


@router.post("/returns/{rid}/email-sent")
def return_email_sent(
    rid: int, email_to: str = Form(""),
    session: Session = Depends(get_session),
):
    ok, msg = services.mark_return_email_sent(session, rid, email_to)
    return _redirect_with_msg(
        f"/purchase/returns/{rid}",
        "success" if ok else "error", msg,
    )


@router.post("/returns/{rid}/confirm")
def return_confirm(
    rid: int,
    signature_note: str = Form(""),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    ok, msg = services.confirm_return(session, rid, signature_note, note)
    return _redirect_with_msg(
        f"/purchase/returns/{rid}",
        "success" if ok else "error", msg,
    )


# ============================================================
# CÔNG NỢ NCC
# ============================================================
@router.get("/supplier-debt")
def supplier_debt(request: Request, session: Session = Depends(get_session)):
    debts = services.get_supplier_debts(session)
    total = sum(d["current_debt"] for d in debts)

    # Đơn quá hạn
    today = datetime.now(timezone.utc).date()
    overdue = []
    for o in services.get_all_orders(session, limit=500):
        if o.due_date and o.due_date < today and o.status in ("RECEIVED", "PARTIAL"):
            sup = services.get_supplier(session, o.supplier_id)
            overdue.append({
                "order": o,
                "supplier": sup,
                "days_overdue": (today - o.due_date).days,
            })
    overdue.sort(key=lambda x: x["days_overdue"], reverse=True)

    return templates.TemplateResponse(
        request=request, name="mua_hang/supplier_debt.html",
        context={
            "debts": debts, "total": total, "overdue": overdue,
        },
    )








# ============================================================
# IN CHỨNG TỪ
# ============================================================
@router.get("/orders/{oid}/print")
def order_print(oid: int, request: Request, session: Session = Depends(get_session)):
    order = services.get_order(session, oid)
    if not order:
        return RedirectResponse(url="/purchase/orders", status_code=303)
    lines = services.get_order_lines(session, oid)
    supplier = services.get_supplier(session, order.supplier_id)

    product_dict = {}
    for l in lines:
        p = session.get(Product, l.product_id)
        if p:
            product_dict[l.product_id] = p

    return templates.TemplateResponse(
        request=request, name="mua_hang/print_order.html",
        context={
            "order": order, "lines": lines,
            "supplier": supplier, "product_dict": product_dict,
        },
    )


@router.get("/orders/{oid}/print-receipt")
def receipt_print(oid: int, request: Request, session: Session = Depends(get_session)):
    order = services.get_order(session, oid)
    if not order:
        return RedirectResponse(url="/purchase/orders", status_code=303)
    lines = services.get_order_lines(session, oid)
    supplier = services.get_supplier(session, order.supplier_id)

    product_dict = {}
    for l in lines:
        p = session.get(Product, l.product_id)
        if p:
            product_dict[l.product_id] = p

    return templates.TemplateResponse(
        request=request, name="mua_hang/print_receipt.html",
        context={
            "order": order, "lines": lines,
            "supplier": supplier, "product_dict": product_dict,
        },
    )


@router.get("/returns/{rid}/print")
def return_print(rid: int, request: Request, session: Session = Depends(get_session)):
    ret = services.get_return(session, rid)
    if not ret:
        return RedirectResponse(url="/purchase/returns", status_code=303)
    lines = services.get_return_lines(session, rid)
    supplier = services.get_supplier(session, ret.supplier_id)

    product_dict = {}
    for l in lines:
        p = session.get(Product, l.product_id)
        if p:
            product_dict[l.product_id] = p

    return templates.TemplateResponse(
        request=request, name="mua_hang/print_return.html",
        context={
            "ret": ret, "lines": lines,
            "supplier": supplier, "product_dict": product_dict,
        },
    )