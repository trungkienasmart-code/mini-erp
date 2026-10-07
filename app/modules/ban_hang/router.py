# app/modules/ban_hang/router.py
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import TEMPLATES_DIR
from app.core.database import get_session
from app.modules.ban_hang import services
from app.modules.ban_hang.schemas import (
    CustomerCreate, CustomerUpdate,
    DiscountCodeCreate, DiscountCodeUpdate,
    ShiftOpen, ShiftClose, ShiftDenominationInput,
    SaleOrderCreate, SaleOrderLineCreate,
    PaymentCreate, ReturnCreate, ReturnLineCreate,
)
from app.modules.quan_ly_kho import services as kho_services

router = APIRouter(prefix="/sales", tags=["Sales"])
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


def _to_float(s, default=0.0):
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# DASHBOARD BÁN HÀNG
# ============================================================
@router.get("/")
def sales_home(request: Request, session: Session = Depends(get_session)):
    # Lấy số liệu tổng quan hôm nay
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    profit = services.report_profit(session, today, datetime.now(timezone.utc))
    order_count = len(services.get_all_orders(session, date_from=today, limit=1000))
    open_shift = services.get_open_shift(session)

    return templates.TemplateResponse(
        request=request, name="ban_hang/home.html",
        context={
            "profit": profit, "order_count": order_count,
            "open_shift": open_shift,
        },
    )


# ============================================================
# CUSTOMER
# ============================================================
@router.get("/customers")
def customer_list(request: Request, q: str = "",
                  session: Session = Depends(get_session)):
    customers = services.get_all_customers(session, keyword=q)
    return templates.TemplateResponse(
        request=request, name="ban_hang/customer_list.html",
        context={"customers": customers, "keyword": q},
    )


@router.get("/customers/new")
def customer_new_form(request: Request):
    return templates.TemplateResponse(
        request=request, name="ban_hang/customer_form.html",
        context={"customer": None, "is_edit": False},
    )


@router.get("/customers/{cid}/edit")
def customer_edit_form(cid: int, request: Request,
                       session: Session = Depends(get_session)):
    c = services.get_customer(session, cid)
    if not c:
        return RedirectResponse(url="/sales/customers", status_code=303)
    return templates.TemplateResponse(
        request=request, name="ban_hang/customer_form.html",
        context={"customer": c, "is_edit": True},
    )


@router.post("/customers/create")
def customer_create(
    code: str = Form(...), name: str = Form(...),
    phone: str = Form(""), email: str = Form(""),
    address: str = Form(""), tax_code: str = Form(""),
    customer_type: str = Form("RETAIL"),
    credit_limit: float = Form(0.0),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    services.create_customer(session, CustomerCreate(
        code=code, name=name, phone=phone, email=email,
        address=address, tax_code=tax_code,
        customer_type=customer_type,
        credit_limit=credit_limit, note=note,
    ))
    return RedirectResponse(url="/sales/customers", status_code=303)


@router.post("/customers/{cid}/update")
def customer_update(
    cid: int,
    code: str = Form(...), name: str = Form(...),
    phone: str = Form(""), email: str = Form(""),
    address: str = Form(""), tax_code: str = Form(""),
    customer_type: str = Form("RETAIL"),
    credit_limit: float = Form(0.0),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    services.update_customer(session, cid, CustomerUpdate(
        code=code, name=name, phone=phone, email=email,
        address=address, tax_code=tax_code,
        customer_type=customer_type,
        credit_limit=credit_limit, note=note,
    ))
    return RedirectResponse(url="/sales/customers", status_code=303)


@router.post("/customers/{cid}/delete")
def customer_delete(cid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_customer(session, cid)
    return _redirect_with_msg("/sales/customers",
                               "success" if ok else "error", msg)


# ============================================================
# DISCOUNT CODE
# ============================================================
@router.get("/discounts")
def discount_list(request: Request, session: Session = Depends(get_session)):
    codes = services.get_all_discount_codes(session)
    return templates.TemplateResponse(
        request=request, name="ban_hang/discount_list.html",
        context={"codes": codes},
    )


@router.get("/discounts/new")
def discount_new_form(request: Request):
    return templates.TemplateResponse(
        request=request, name="ban_hang/discount_form.html",
        context={"code": None, "is_edit": False},
    )


@router.get("/discounts/{did}/edit")
def discount_edit_form(did: int, request: Request,
                       session: Session = Depends(get_session)):
    d = services.get_discount_code(session, did)
    if not d:
        return RedirectResponse(url="/sales/discounts", status_code=303)
    return templates.TemplateResponse(
        request=request, name="ban_hang/discount_form.html",
        context={"code": d, "is_edit": True},
    )


@router.post("/discounts/create")
def discount_create(
    code: str = Form(...), name: str = Form(...),
    discount_type: str = Form("PERCENT"),
    discount_value: float = Form(0.0),
    max_discount: float = Form(0.0),
    min_order_amount: float = Form(0.0),
    apply_to: str = Form("ALL"),
    max_uses: int = Form(0),
    requires_approval: bool = Form(False),
    status: str = Form("ACTIVE"),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    services.create_discount_code(session, DiscountCodeCreate(
        code=code, name=name, discount_type=discount_type,
        discount_value=discount_value, max_discount=max_discount,
        min_order_amount=min_order_amount, apply_to=apply_to,
        max_uses=max_uses, requires_approval=requires_approval,
        status=status, note=note,
    ))
    return RedirectResponse(url="/sales/discounts", status_code=303)


@router.post("/discounts/{did}/delete")
def discount_delete(did: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_discount_code(session, did)
    return _redirect_with_msg("/sales/discounts",
                               "success" if ok else "error", msg)


# ============================================================
# API: Lookup barcode / sản phẩm (cho POS)
# ============================================================
@router.get("/api/lookup-barcode")
def api_lookup_barcode(code: str, session: Session = Depends(get_session)):
    """Tra mã vạch → trả về sản phẩm + UoM + giá."""
    from app.modules.quan_ly_kho.models import Barcode, Product
    bc = session.exec(
        __import__('sqlmodel').select(Barcode).where(Barcode.code == code)
    ).first()

    if not bc:
        return JSONResponse({"found": False, "message": "Không tìm thấy mã vạch"})

    p = session.get(Product, bc.product_id)
    if not p:
        return JSONResponse({"found": False, "message": "Sản phẩm không tồn tại"})

    # Xác định giá và factor theo UoM
    price = p.price
    factor = 1
    uom_name = p.unit
    if bc.uom_id:
        uom = session.exec(
            __import__('sqlmodel').select(__import__('app.modules.quan_ly_kho.models', fromlist=['ProductUoM']).ProductUoM).where(
                __import__('app.modules.quan_ly_kho.models', fromlist=['ProductUoM']).ProductUoM.id == bc.uom_id
            )
        ).first()
        if uom:
            price = uom.sale_price or p.price
            factor = uom.factor
            uom_name = uom.name

    return JSONResponse({
        "found": True,
        "product_id": p.id,
        "sku": p.sku,
        "name": p.name,
        "unit": p.unit,
        "uom_id": bc.uom_id,
        "uom_name": uom_name,
        "factor": factor,
        "price": price,
        "tax_rate": p.tax_rate,
        "stock": p.stock_quantity,
    })


@router.get("/api/search-product")
def api_search_product(q: str, session: Session = Depends(get_session)):
    """Tìm sản phẩm theo tên/mã SKU."""
    products_data = kho_services.search_products(session, keyword=q)
    results = []
    for p, cat in products_data[:20]:
        results.append({
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "unit": p.unit,
            "price": p.price,
            "tax_rate": p.tax_rate,
            "stock": p.stock_quantity,
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

@router.get("/api/vat-customer")
def api_lookup_vat_customer(tax_code: str, session: Session = Depends(get_session)):
    """Tra cứu thông tin KH VAT theo MST (auto-fill cho POS)."""
    vc = services.lookup_vat_customer(session, tax_code)
    if not vc:
        return JSONResponse({"found": False})
    return JSONResponse({
        "found": True,
        "tax_code": vc.tax_code,
        "company_name": vc.company_name,
        "address": vc.address,
        "email": vc.email,
        "phone": vc.phone,
    })

# ============================================================
# POS — MÀN HÌNH BÁN HÀNG
# ============================================================
@router.get("/pos")
def pos_screen(request: Request, session: Session = Depends(get_session)):
    # Kiểm tra có ca mở không
    open_shift = services.get_open_shift(session)
    if not open_shift:
        return RedirectResponse(url="/sales/shift/open", status_code=303)

    # Load danh sách SP (30 SP đầu để hiển thị grid)
    products_data = kho_services.search_products(session, keyword="")
    products = []
    for p, cat in products_data[:60]:
        products.append({
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "price": p.price,
            "tax_rate": p.tax_rate, "stock": p.stock_quantity,
            "category": cat.name if cat else "Khác",
        })

    default_cust = services.get_default_customer(session)
    customers = services.get_all_customers(session)

    return templates.TemplateResponse(
        request=request, name="ban_hang/pos.html",
        context={
            "products": products,
            "customers": customers,
            "default_customer": default_cust,
            "open_shift": open_shift,
        },
    )


@router.post("/pos/checkout")
async def pos_checkout(request: Request, session: Session = Depends(get_session)):
    """Xử lý thanh toán POS. Nhận JSON từ frontend."""
    body = await request.json()

    try:
        lines_data = []
        for item in body.get("lines", []):
            lines_data.append(SaleOrderLineCreate(
                product_id=int(item["product_id"]),
                uom_id=_to_int_or_none(item.get("uom_id")),
                quantity=int(item["quantity"]),
                unit_price=_to_float(item.get("unit_price")),
                discount_percent=_to_float(item.get("discount_percent")),
                tax_rate=_to_float(item.get("tax_rate")),
            ))

        order_data = SaleOrderCreate(
            customer_id=_to_int_or_none(body.get("customer_id")),
            order_type="POS",
            payment_method=body.get("payment_method", "CASH"),
            discount_code_id=_to_int_or_none(body.get("discount_code_id")),
            discount_amount=_to_float(body.get("discount_amount", 0)),
            note=body.get("note", ""),
            lines=lines_data,
            want_vat_invoice=bool(body.get("want_vat_invoice", False)),
            vat_company_name=body.get("vat_company_name", ""),
            vat_tax_code=body.get("vat_tax_code", ""),
            vat_address=body.get("vat_address", ""),
            vat_email=body.get("vat_email", ""),
            customer_phone=body.get("customer_phone", ""),
            paid_amount=_to_float(body.get("paid_amount", 0)),
	    customer_paid=_to_float(body.get("customer_paid", 0)),
        )

        order, msg = services.create_sale_order(session, order_data, auto_confirm=True)
        if not order:
            return JSONResponse({"success": False, "message": msg}, status_code=400)

        # Cập nhật SĐT vào KH nếu có và KH mặc định
        if order_data.customer_phone and order.customer_id:
            cust = services.get_customer(session, order.customer_id)
            if cust and not cust.phone:
                cust.phone = order_data.customer_phone
                session.add(cust)
                session.commit()

        return JSONResponse({
            "success": True,
            "order_id": order.id,
            "order_code": order.code,
            "total": order.total_amount,
            "print_url": f"/sales/orders/{order.id}/print",
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)


# ============================================================
# SHIFT
# ============================================================
@router.get("/shift/open")
def shift_open_form(request: Request, session: Session = Depends(get_session)):
    existing = services.get_open_shift(session)
    if existing:
        return RedirectResponse(url="/sales/pos", status_code=303)
    return templates.TemplateResponse(
        request=request, name="ban_hang/shift_open.html", context={},
    )


@router.post("/shift/open")
def shift_open(
    opening_cash: float = Form(0.0),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    services.open_shift(session, ShiftOpen(opening_cash=opening_cash, note=note))
    return RedirectResponse(url="/sales/pos", status_code=303)


@router.get("/shift/close")
def shift_close_form(request: Request, session: Session = Depends(get_session)):
    shift = services.get_open_shift(session)
    if not shift:
        return RedirectResponse(url="/sales/pos", status_code=303)

    from app.modules.ke_toan.services import get_all_cash_accounts
    cash_accounts = get_all_cash_accounts(session, only_active=True)
    cash_list = [a for a in cash_accounts if a.account_type == "CASH"]
    bank_list = [a for a in cash_accounts if a.account_type == "BANK"]

    return templates.TemplateResponse(
        request=request, name="ban_hang/shift_close.html",
        context={
            "shift": shift,
            "cash_list": cash_list,
            "bank_list": bank_list,
        },
    )

@router.post("/shift/preview-close")
async def shift_preview_close(request: Request, session: Session = Depends(get_session)):
    """Xem trước số liệu đóng ca (chưa commit)."""
    body = await request.json()
    shift = services.get_open_shift(session)
    if not shift:
        return JSONResponse({"ok": False, "message": "Không có ca đang mở"},
                             status_code=400)

    # Cập nhật counted_cash tạm để tính
    from decimal import Decimal
    counted = _to_float(body.get("counted_cash", 0))

    # Tạm gán để preview tính
    shift.counted_cash = counted
    session.add(shift)
    session.flush()

    result = services.preview_close_shift(session, shift.id)
    session.rollback()  # Không commit
    return JSONResponse(result)


@router.post("/shift/close")
async def shift_close(request: Request, session: Session = Depends(get_session)):
    """Đóng ca. Nhận JSON từ form."""
    body = await request.json()
    shift = services.get_open_shift(session)
    if not shift:
        return JSONResponse({"success": False, "message": "Không có ca đang mở"},
                             status_code=400)

    denoms = []
    for d in body.get("denominations", []):
        denoms.append(ShiftDenominationInput(
            denomination=int(d["denomination"]),
            quantity=int(d["quantity"]),
        ))

    data = ShiftClose(
        denominations=denoms,
        counted_cash=_to_float(body.get("counted_cash", 0)),
        cash_account_id=_to_int_or_none(body.get("cash_account_id")),
        bank_account_id=_to_int_or_none(body.get("bank_account_id")),
        note=body.get("note", ""),
    )
    ok, msg, s = services.close_shift(session, shift.id, data)
    if not ok:
        return JSONResponse({"success": False, "message": msg}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": msg,
        "shift_id": s.id,
        "report_url": f"/sales/shifts/{s.id}",
    })


@router.get("/shifts")
def shift_list(request: Request, session: Session = Depends(get_session)):
    shifts = services.get_all_shifts(session)
    return templates.TemplateResponse(
        request=request, name="ban_hang/shift_list.html",
        context={"shifts": shifts},
    )


@router.get("/shifts/{sid}")
def shift_detail(sid: int, request: Request,
                 session: Session = Depends(get_session)):
    shift = services.get_shift(session, sid)
    if not shift:
        return RedirectResponse(url="/sales/shifts", status_code=303)

    # Nếu ca đang mở → tính live revenue
    if shift.status == "OPEN":
        from app.modules.ban_hang.models import SaleOrder as SO, SalePayment as SP
        from sqlmodel import select as sel, func as fn

        orders = session.exec(
            sel(SO).where(SO.shift_id == sid).where(SO.status != "CANCELLED")
        ).all()
        shift.total_revenue = sum(o.total_amount for o in orders)

        payments = session.exec(
            sel(SP).join(SO, SP.order_id == SO.id).where(SO.shift_id == sid)
        ).all()
        shift.total_cash_sales = sum(p.amount for p in payments if p.payment_method == "CASH")
        shift.total_bank_sales = sum(p.amount for p in payments if p.payment_method == "BANK")
        shift.total_card_sales = sum(p.amount for p in payments if p.payment_method == "CARD")
        shift.total_debt_sales = sum(p.amount for p in payments if p.payment_method == "DEBT")

    denoms = services.get_shift_denominations(session, sid)
    return templates.TemplateResponse(
        request=request, name="ban_hang/shift_detail.html",
        context={"shift": shift, "denominations": denoms},
    )


# ============================================================
# ORDERS
# ============================================================
@router.get("/orders")
def order_list(request: Request, q: str = "", status: str = "",
               session: Session = Depends(get_session)):
    orders = services.get_all_orders(session, keyword=q, status=status)
    # Map customer name
    cust_dict = {}
    for c in services.get_all_customers(session):
        cust_dict[c.id] = c.name
    return templates.TemplateResponse(
        request=request, name="ban_hang/order_list.html",
        context={"orders": orders, "keyword": q, "status": status,
                 "customer_dict": cust_dict},
    )


@router.get("/orders/new")
def order_new_form(request: Request, session: Session = Depends(get_session)):
    customers = services.get_all_customers(session)
    products_data = kho_services.search_products(session, keyword="")
    products = []
    for p, cat in products_data[:100]:
        products.append({
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "price": p.price,
            "tax_rate": p.tax_rate, "stock": p.stock_quantity,
        })
    return templates.TemplateResponse(
        request=request, name="ban_hang/order_form.html",
        context={"customers": customers, "products": products, "order": None,
                 "is_edit": False},
    )


@router.get("/orders/{oid}")
def order_detail(oid: int, request: Request,
                 session: Session = Depends(get_session)):
    order = services.get_order(session, oid)
    if not order:
        return RedirectResponse(url="/sales/orders", status_code=303)
    lines = services.get_order_lines(session, oid)
    payments = services.get_order_payments(session, oid)

    products_dict = {}
    for l in lines:
        p = session.get(__import__('app.modules.quan_ly_kho.models', fromlist=['Product']).Product, l.product_id)
        if p:
            products_dict[l.product_id] = f"{p.sku} - {p.name}"

    customer = services.get_customer(session, order.customer_id) if order.customer_id else None

    # Lấy danh sách tài khoản quỹ
    from app.modules.ke_toan.services import get_all_cash_accounts
    cash_accounts = get_all_cash_accounts(session, only_active=True)

    return templates.TemplateResponse(
        request=request, name="ban_hang/order_detail.html",
        context={
            "order": order, "lines": lines, "payments": payments,
            "customer": customer, "product_dict": products_dict,
            "cash_accounts": cash_accounts,
        },
    )


@router.post("/orders/{oid}/payment")
def order_add_payment(
    oid: int,
    amount: float = Form(...),
    payment_method: str = Form("CASH"),
    cash_account_id: str = Form(""),
    bank_transaction_code: str = Form(""),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    ok, msg = services.add_payment(session, PaymentCreate(
        order_id=oid, amount=amount, payment_method=payment_method,
        cash_account_id=_to_int_or_none(cash_account_id),
        bank_transaction_code=bank_transaction_code, note=note,
    ))
    return _redirect_with_msg(f"/sales/orders/{oid}",
                               "success" if ok else "error", msg)


@router.post("/orders/{oid}/cancel")
def order_cancel(oid: int, session: Session = Depends(get_session)):
    """Hủy đơn hàng (chỉ khi DRAFT/CONFIRMED, chưa thanh toán gì)."""
    order = services.get_order(session, oid)
    if not order:
        return _redirect_with_msg("/sales/orders", "error", "Đơn không tồn tại")
    if order.paid_amount > 0:
        return _redirect_with_msg(f"/sales/orders/{oid}", "error",
                                   "Không thể hủy: Đã có thanh toán")
    if order.status == "CANCELLED":
        return _redirect_with_msg(f"/sales/orders/{oid}", "error",
                                   "Đơn đã hủy")

    # Hoàn kho: xóa các stock_move liên kết
    for line in services.get_order_lines(session, oid):
        if line.stock_move_id:
            # Force delete để tránh vấn đề layer
            kho_services.force_delete_move_with_replay(session, line.stock_move_id)

    order.status = "CANCELLED"
    session.add(order)
    session.commit()
    return _redirect_with_msg(f"/sales/orders/{oid}", "success", "Đã hủy đơn")


# ============================================================
# IN HÓA ĐƠN
# ============================================================
@router.get("/orders/{oid}/print")
def order_print(oid: int, request: Request, size: str = "k80",
                session: Session = Depends(get_session)):
    order = services.get_order(session, oid)
    if not order:
        return RedirectResponse(url="/sales/orders", status_code=303)
    lines = services.get_order_lines(session, oid)
    customer = services.get_customer(session, order.customer_id) if order.customer_id else None

    products_dict = {}
    for l in lines:
        p = session.get(__import__('app.modules.quan_ly_kho.models', fromlist=['Product']).Product, l.product_id)
        if p:
            products_dict[l.product_id] = p

    # Chọn template theo size
    tpl = "ban_hang/print_k80.html" if size == "k80" else "ban_hang/print_a5.html"

    return templates.TemplateResponse(
        request=request, name=tpl,
        context={
            "order": order, "lines": lines, "customer": customer,
            "product_dict": products_dict, "size": size,
        },
    )


# ============================================================
# RETURNS
# ============================================================
@router.get("/returns")
def return_list(request: Request, session: Session = Depends(get_session)):
    returns = services.get_all_returns(session)
    return templates.TemplateResponse(
        request=request, name="ban_hang/return_list.html",
        context={"returns": returns},
    )


@router.get("/returns/new")
def return_new_form(request: Request, order_id: str = "",
                    session: Session = Depends(get_session)):
    customers = services.get_all_customers(session)
    products_data = kho_services.search_products(session, keyword="")
    products = []
    for p, cat in products_data[:100]:
        products.append({
            "id": p.id, "sku": p.sku, "name": p.name,
            "unit": p.unit, "price": p.price,
            "tax_rate": p.tax_rate, "stock": p.stock_quantity,
        })
    return templates.TemplateResponse(
        request=request, name="ban_hang/return_form.html",
        context={"customers": customers, "products": products,
                 "original_order_id": _to_int_or_none(order_id)},
    )

@router.post("/returns/create")
async def return_create(request: Request, session: Session = Depends(get_session)):
    """Tạo phiếu trả hàng. Nhận JSON."""
    body = await request.json()
    try:
        lines = []
        for item in body.get("lines", []):
            lines.append(ReturnLineCreate(
                product_id=int(item["product_id"]),
                uom_id=_to_int_or_none(item.get("uom_id")),
                quantity=int(item["quantity"]),
                unit_price=_to_float(item.get("unit_price")),
                reason=item.get("reason", ""),
            ))

        data = ReturnCreate(
            original_order_id=_to_int_or_none(body.get("original_order_id")),
            customer_id=_to_int_or_none(body.get("customer_id")),
            refund_method=body.get("refund_method", "CASH"),
            reason=body.get("reason", ""),
            note=body.get("note", ""),
            lines=lines,
        )
        ret, msg = services.create_return(session, data)
        if not ret:
            return JSONResponse({"success": False, "message": msg}, status_code=400)
        return JSONResponse({
            "success": True, "return_id": ret.id, "return_code": ret.code,
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)


@router.get("/returns/{rid}")
def return_detail(rid: int, request: Request,
                  session: Session = Depends(get_session)):
    ret = services.get_return(session, rid)
    if not ret:
        return RedirectResponse(url="/sales/returns", status_code=303)
    lines = services.get_return_lines(session, rid)

    products_dict = {}
    for l in lines:
        p = session.get(__import__('app.modules.quan_ly_kho.models', fromlist=['Product']).Product, l.product_id)
        if p:
            products_dict[l.product_id] = f"{p.sku} - {p.name}"

    customer = services.get_customer(session, ret.customer_id) if ret.customer_id else None

    return templates.TemplateResponse(
        request=request, name="ban_hang/return_detail.html",
        context={"ret": ret, "lines": lines, "customer": customer,
                 "product_dict": products_dict},
    )


# ============================================================
# BÁO CÁO
# ============================================================
@router.get("/reports")
def reports(request: Request, session: Session = Depends(get_session)):
    # Mặc định: hôm nay
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)
    daily = services.report_daily_revenue(session, today, now)
    top = services.report_top_products(session, today, now, limit=10)
    profit = services.report_profit(session, today, now)

    return templates.TemplateResponse(
        request=request, name="ban_hang/reports.html",
        context={"daily": daily, "top": top, "profit": profit},
    )


@router.get("/reports/range")
def reports_range(
    request: Request,
    date_from: str = "",
    date_to: str = "",
    session: Session = Depends(get_session),
):
    try:
        if date_from:
            df = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            df = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to:
            dt = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
    except ValueError:
        df = datetime.now(timezone.utc) - timedelta(days=30)
        dt = datetime.now(timezone.utc)

    daily = services.report_daily_revenue(session, df, dt)
    top = services.report_top_products(session, df, dt, limit=20)
    profit = services.report_profit(session, df, dt)

    return templates.TemplateResponse(
        request=request, name="ban_hang/reports.html",
        context={
            "daily": daily, "top": top, "profit": profit,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
        },
    )