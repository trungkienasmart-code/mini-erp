# app/modules/ke_toan/router.py
from datetime import datetime, date, timezone
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from sqlmodel import Session

from app.core.templates import templates
from app.core.database import get_session
from app.modules.ke_toan import services
from app.modules.ke_toan.schemas import (
    HKDProfileCreate, HKDProfileUpdate,
    CashAccountCreate, CashAccountUpdate,
    VoucherCreate,
    FixedAssetCreate, FixedAssetUpdate, AssetDisposal,
    PeriodLockCreate,
)

router = APIRouter(prefix="/accounting", tags=["Accounting"])


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


def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except ValueError:
        return None


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


def _default_date_range():
    """Trả về ngày đầu tháng và hôm nay."""
    today = date.today()
    return today.replace(day=1), today


# ============================================================
# DASHBOARD KẾ TOÁN
# ============================================================
@router.get("/")
def accounting_home(request: Request, session: Session = Depends(get_session)):
    profile = services.get_hkd_profile(session)
    accounts = services.get_all_cash_accounts(session, only_active=True)

    total_cash = sum(a.current_balance for a in accounts if a.account_type == "CASH")
    total_bank = sum(a.current_balance for a in accounts if a.account_type == "BANK")

    # Doanh thu hôm nay
    today = date.today()
    df, dt = _default_date_range()
    tax_summary = services.report_tax_summary(session, df, dt)

    # Công nợ
    debt = services.report_debt_summary(session)

    # Tài sản
    assets = services.get_all_assets(session, status="ACTIVE")

    return templates.TemplateResponse(
        request=request, name="ke_toan/home.html",
        context={
            "profile": profile,
            "total_cash": total_cash,
            "total_bank": total_bank,
            "account_count": len(accounts),
            "tax_summary": tax_summary,
            "debt": debt,
            "asset_count": len(assets),
        },
    )


# ============================================================
# HKD PROFILE / SETTINGS
# ============================================================
@router.get("/settings")
def settings_form(request: Request, session: Session = Depends(get_session)):
    profile = services.get_hkd_profile(session)
    return templates.TemplateResponse(
        request=request, name="ke_toan/settings.html",
        context={"profile": profile},
    )


@router.post("/settings")
def settings_save(
    business_name: str = Form(...),
    tax_code: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    hkd_group: int = Form(1),
    vat_rate_retail: float = Form(1.0),
    vat_rate_service: float = Form(5.0),
    tncn_rate: float = Form(0.5),
    has_other_taxes: bool = Form(False),
    opening_cash: float = Form(0.0),
    opening_bank: float = Form(0.0),
    fiscal_year_start: str = Form("01-01"),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    profile = services.create_or_update_hkd_profile(session, HKDProfileCreate(
        business_name=business_name, tax_code=tax_code,
        address=address, phone=phone, email=email,
        hkd_group=hkd_group,
        vat_rate_retail=vat_rate_retail,
        vat_rate_service=vat_rate_service,
        tncn_rate=tncn_rate,
        has_other_taxes=has_other_taxes,
        opening_cash=opening_cash,
        opening_bank=opening_bank,
        fiscal_year_start=fiscal_year_start,
        note=note,
    ))
    return _redirect_with_msg("/accounting/settings", "success", "Đã lưu cấu hình HKD")


# ============================================================
# PERIOD LOCK
# ============================================================
@router.get("/periods")
def periods_list(request: Request, session: Session = Depends(get_session)):
    locks = services.get_all_period_locks(session)
    return templates.TemplateResponse(
        request=request, name="ke_toan/periods.html",
        context={"locks": locks},
    )


@router.post("/periods/lock")
def period_lock(
    period: str = Form(...), note: str = Form(""),
    session: Session = Depends(get_session),
):
    ok, msg = services.lock_period(session, PeriodLockCreate(period=period, note=note))
    return _redirect_with_msg("/accounting/periods",
                               "success" if ok else "error", msg)


@router.post("/periods/{period}/unlock")
def period_unlock(period: str, session: Session = Depends(get_session)):
    ok, msg = services.unlock_period(session, period)
    return _redirect_with_msg("/accounting/periods",
                               "success" if ok else "error", msg)


# ============================================================
# CASH ACCOUNTS
# ============================================================
@router.get("/cash-accounts")
def cash_account_list(request: Request, session: Session = Depends(get_session)):
    accounts = services.get_all_cash_accounts(session)
    return templates.TemplateResponse(
        request=request, name="ke_toan/cash_account_list.html",
        context={"accounts": accounts},
    )


@router.get("/cash-accounts/new")
def cash_account_new_form(request: Request):
    return templates.TemplateResponse(
        request=request, name="ke_toan/cash_account_form.html",
        context={"account": None, "is_edit": False},
    )


@router.get("/cash-accounts/{cid}/edit")
def cash_account_edit_form(cid: int, request: Request,
                            session: Session = Depends(get_session)):
    acc = services.get_cash_account(session, cid)
    if not acc:
        return RedirectResponse(url="/accounting/cash-accounts", status_code=303)
    return templates.TemplateResponse(
        request=request, name="ke_toan/cash_account_form.html",
        context={"account": acc, "is_edit": True},
    )


@router.post("/cash-accounts/create")
def cash_account_create(
    code: str = Form(...), name: str = Form(...),
    account_type: str = Form("CASH"),
    bank_name: str = Form(""), bank_account_no: str = Form(""),
    bank_branch: str = Form(""),
    opening_balance: float = Form(0.0),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    services.create_cash_account(session, CashAccountCreate(
        code=code, name=name, account_type=account_type,
        bank_name=bank_name, bank_account_no=bank_account_no,
        bank_branch=bank_branch, opening_balance=opening_balance, note=note,
    ))
    return RedirectResponse(url="/accounting/cash-accounts", status_code=303)


@router.post("/cash-accounts/{cid}/update")
def cash_account_update(
    cid: int,
    code: str = Form(...), name: str = Form(...),
    account_type: str = Form("CASH"),
    bank_name: str = Form(""), bank_account_no: str = Form(""),
    bank_branch: str = Form(""),
    opening_balance: float = Form(0.0),
    note: str = Form(""), status: str = Form("ACTIVE"),
    session: Session = Depends(get_session),
):
    services.update_cash_account(session, cid, CashAccountUpdate(
        code=code, name=name, account_type=account_type,
        bank_name=bank_name, bank_account_no=bank_account_no,
        bank_branch=bank_branch, opening_balance=opening_balance,
        note=note, status=status,
    ))
    return RedirectResponse(url="/accounting/cash-accounts", status_code=303)


@router.post("/cash-accounts/{cid}/delete")
def cash_account_delete(cid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_cash_account(session, cid)
    return _redirect_with_msg("/accounting/cash-accounts",
                               "success" if ok else "error", msg)


# ============================================================
# VOUCHERS
# ============================================================
@router.get("/vouchers")
def voucher_list(
    request: Request,
    voucher_type: str = "",
    cash_account_id: str = "",
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()

    vouchers = services.get_all_vouchers(
        session,
        voucher_type=voucher_type,
        cash_account_id=_to_int_or_none(cash_account_id),
        date_from=df, date_to=dt,
    )
    accounts = services.get_all_cash_accounts(session, only_active=True)
    account_dict = {a.id: a.name for a in accounts}

    # Tổng thu/chi
    total_receipt = sum(v.amount for v in vouchers if v.voucher_type == "RECEIPT")
    total_payment = sum(v.amount for v in vouchers if v.voucher_type == "PAYMENT")

    return templates.TemplateResponse(
        request=request, name="ke_toan/voucher_list.html",
        context={
            "vouchers": vouchers,
            "accounts": accounts,
            "account_dict": account_dict,
            "voucher_type": voucher_type,
            "filter_cash_id": _to_int_or_none(cash_account_id),
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
            "total_receipt": total_receipt,
            "total_payment": total_payment,
        },
    )


@router.get("/vouchers/new")
def voucher_new_form(
    request: Request, voucher_type: str = "RECEIPT",
    session: Session = Depends(get_session),
):
    accounts = services.get_all_cash_accounts(session, only_active=True)
    return templates.TemplateResponse(
        request=request, name="ke_toan/voucher_form.html",
        context={
            "voucher": None, "is_edit": False,
            "accounts": accounts,
            "default_type": voucher_type,
        },
    )


@router.post("/vouchers/create")
def voucher_create(
    voucher_type: str = Form(...),
    cash_account_id: int = Form(...),
    partner_type: str = Form("OTHER"),
    partner_name: str = Form(""),
    amount: float = Form(...),
    category: str = Form(""),
    reason: str = Form(""),
    note: str = Form(""),
    voucher_date: str = Form(""),
    session: Session = Depends(get_session),
):
    data = VoucherCreate(
        voucher_type=voucher_type,
        cash_account_id=cash_account_id,
        partner_type=partner_type,
        partner_name=partner_name,
        amount=amount,
        category=category,
        reason=reason,
        note=note,
        voucher_date=_to_date(voucher_date),
    )
    voucher, msg = services.create_voucher(session, data)
    if not voucher:
        return _redirect_with_msg("/accounting/vouchers", "error", msg)
    return _redirect_with_msg("/accounting/vouchers", "success",
                               f"Đã tạo phiếu {voucher.code}")

# ============================================================
# EXPORT CSV
# ============================================================
@router.get("/vouchers/export")
def vouchers_export(
    voucher_type: str = "",
    cash_account_id: str = "",
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    import csv, io

    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()

    vouchers = services.get_all_vouchers(
        session, voucher_type=voucher_type,
        cash_account_id=_to_int_or_none(cash_account_id),
        date_from=df, date_to=dt,
    )
    accounts = services.get_all_cash_accounts(session)
    account_dict = {a.id: a.name for a in accounts}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Mã phiếu", "Ngày", "Loại", "Tài khoản quỹ",
                     "Đối tượng", "Số tiền", "Khoản mục", "Lý do", "Ghi chú"])

    for v in vouchers:
        writer.writerow([
            v.code,
            v.voucher_date.strftime("%Y-%m-%d"),
            "Thu" if v.voucher_type == "RECEIPT" else "Chi",
            account_dict.get(v.cash_account_id, ""),
            v.partner_name,
            f"{v.amount:.0f}",
            v.category or "",
            v.reason,
            v.note,
        ])

    csv_content = "\ufeff" + output.getvalue()
    filename = f"vouchers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/vouchers/{vid}")
def voucher_detail(vid: int, request: Request,
                   session: Session = Depends(get_session)):
    voucher = services.get_voucher(session, vid)
    if not voucher:
        return RedirectResponse(url="/accounting/vouchers", status_code=303)
    acc = services.get_cash_account(session, voucher.cash_account_id)
    return templates.TemplateResponse(
        request=request, name="ke_toan/voucher_detail.html",
        context={"voucher": voucher, "account": acc},
    )


@router.post("/vouchers/{vid}/delete")
def voucher_delete(vid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_voucher(session, vid)
    return _redirect_with_msg("/accounting/vouchers",
                               "success" if ok else "error", msg)


# ============================================================
# FIXED ASSETS
# ============================================================
@router.get("/assets")
def asset_list(
    request: Request,
    asset_type: str = "", status: str = "",
    session: Session = Depends(get_session),
):
    assets = services.get_all_assets(session, asset_type=asset_type, status=status)
    return templates.TemplateResponse(
        request=request, name="ke_toan/asset_list.html",
        context={
            "assets": assets,
            "filter_type": asset_type,
            "filter_status": status,
        },
    )


@router.get("/assets/new")
def asset_new_form(request: Request):
    return templates.TemplateResponse(
        request=request, name="ke_toan/asset_form.html",
        context={"asset": None, "is_edit": False},
    )


@router.get("/assets/{aid}/edit")
def asset_edit_form(aid: int, request: Request,
                    session: Session = Depends(get_session)):
    asset = services.get_asset(session, aid)
    if not asset:
        return RedirectResponse(url="/accounting/assets", status_code=303)
    return templates.TemplateResponse(
        request=request, name="ke_toan/asset_form.html",
        context={"asset": asset, "is_edit": True},
    )


@router.get("/assets/{aid}")
def asset_detail(aid: int, request: Request,
                 session: Session = Depends(get_session)):
    asset = services.get_asset(session, aid)
    if not asset:
        return RedirectResponse(url="/accounting/assets", status_code=303)
    deps = services.get_asset_depreciations(session, aid)
    return templates.TemplateResponse(
        request=request, name="ke_toan/asset_detail.html",
        context={"asset": asset, "depreciations": deps},
    )


@router.post("/assets/create")
def asset_create(
    code: str = Form(""), name: str = Form(...),
    asset_type: str = Form("TSCD"),
    unit: str = Form("Cái"), quantity: int = Form(1),
    original_cost: float = Form(0.0),
    depreciation_rate: float = Form(0.0),
    purchase_date: str = Form(""), start_use_date: str = Form(""),
    location: str = Form(""), note: str = Form(""),
    session: Session = Depends(get_session),
):
    data = FixedAssetCreate(
        code=code, name=name, asset_type=asset_type,
        unit=unit, quantity=quantity,
        original_cost=original_cost,
        depreciation_rate=depreciation_rate,
        purchase_date=_to_date(purchase_date),
        start_use_date=_to_date(start_use_date),
        location=location, note=note,
    )
    asset, msg = services.create_asset(session, data)
    if not asset:
        return _redirect_with_msg("/accounting/assets", "error", msg)
    return RedirectResponse(url=f"/accounting/assets/{asset.id}", status_code=303)


@router.post("/assets/{aid}/update")
def asset_update(
    aid: int,
    code: str = Form(""), name: str = Form(...),
    asset_type: str = Form("TSCD"),
    unit: str = Form("Cái"), quantity: int = Form(1),
    original_cost: float = Form(0.0),
    depreciation_rate: float = Form(0.0),
    purchase_date: str = Form(""), start_use_date: str = Form(""),
    location: str = Form(""), note: str = Form(""),
    session: Session = Depends(get_session),
):
    services.update_asset(session, aid, FixedAssetUpdate(
        code=code, name=name, asset_type=asset_type,
        unit=unit, quantity=quantity,
        original_cost=original_cost,
        depreciation_rate=depreciation_rate,
        purchase_date=_to_date(purchase_date),
        start_use_date=_to_date(start_use_date),
        location=location, note=note,
    ))
    return RedirectResponse(url=f"/accounting/assets/{aid}", status_code=303)


@router.post("/assets/{aid}/dispose")
def asset_dispose(
    aid: int,
    disposal_date: str = Form(...),
    disposal_reason: str = Form(""),
    disposal_value: float = Form(0.0),
    session: Session = Depends(get_session),
):
    ok, msg = services.dispose_asset(session, aid, AssetDisposal(
        disposal_date=_to_date(disposal_date),
        disposal_reason=disposal_reason,
        disposal_value=disposal_value,
    ))
    return _redirect_with_msg(f"/accounting/assets/{aid}",
                               "success" if ok else "error", msg)


@router.post("/assets/{aid}/delete")
def asset_delete(aid: int, session: Session = Depends(get_session)):
    ok, msg = services.delete_asset(session, aid)
    return _redirect_with_msg("/accounting/assets",
                               "success" if ok else "error", msg)

@router.post("/assets/{aid}/reset-depreciation")
def asset_reset_depreciation(aid: int, session: Session = Depends(get_session)):
    """Reset toàn bộ khấu hao của 1 tài sản."""
    ok, msg = services.delete_asset_depreciations(session, aid)
    return _redirect_with_msg(f"/accounting/assets/{aid}",
                               "success" if ok else "error", msg)


# ============================================================
# KHẤU HAO
# ============================================================
@router.get("/depreciation")
def depreciation_page(request: Request, session: Session = Depends(get_session)):
    # Lấy danh sách tháng gần đây
    today = date.today()
    months = []
    for i in range(12):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")
    return templates.TemplateResponse(
        request=request, name="ke_toan/depreciation.html",
        context={"months": months},
    )


@router.post("/depreciation/run")
def depreciation_run(
    period: str = Form(...),
    session: Session = Depends(get_session),
):
    count, msg = services.run_monthly_depreciation(session, period)
    return _redirect_with_msg("/accounting/depreciation",
                               "success" if count > 0 else "error", msg)

@router.post("/depreciation/reset")
def depreciation_reset(period: str = Form(...), session: Session = Depends(get_session)):
    """Xóa toàn bộ khấu hao của 1 kỳ."""
    ok, msg = services.delete_depreciation_by_period(session, period)
    return _redirect_with_msg("/accounting/depreciation",
                               "success" if ok else "error", msg)

# ============================================================
# BÁO CÁO / SỔ SÁCH
# ============================================================
@router.get("/reports")
def reports_home(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request=request, name="ke_toan/reports.html",
        context={},
    )


@router.get("/reports/s1a")
def report_s1a(
    request: Request,
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()
    rows = services.report_s1a_s2a_s2b_revenue(session, df, dt)
    profile = services.get_hkd_profile(session)
    total = sum(r["amount"] for r in rows)
    return templates.TemplateResponse(
        request=request, name="ke_toan/report_s1a.html",
        context={
            "rows": rows, "total": total,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
            "profile": profile,
        },
    )


@router.get("/reports/s2a")
def report_s2a(
    request: Request,
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()
    rows = services.report_s1a_s2a_s2b_revenue(session, df, dt)
    profile = services.get_hkd_profile(session)
    total = sum(r["amount"] for r in rows)
    return templates.TemplateResponse(
        request=request, name="ke_toan/report_s2a.html",
        context={
            "rows": rows, "total": total,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
            "profile": profile,
        },
    )


@router.get("/reports/s2c")
def report_s2c(
    request: Request,
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()
    rows = services.report_s2c_revenue_expense(session, df, dt)
    profile = services.get_hkd_profile(session)
    total_rev = sum(r["revenue"] for r in rows)
    total_exp = sum(r["expense"] for r in rows)
    return templates.TemplateResponse(
        request=request, name="ke_toan/report_s2c.html",
        context={
            "rows": rows,
            "total_revenue": total_rev,
            "total_expense": total_exp,
            "total_profit": total_rev - total_exp,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
            "profile": profile,
        },
    )


@router.get("/reports/s2d")
def report_s2d(
    request: Request,
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    """Sổ chi tiết vật tư, hàng hóa — lấy dữ liệu từ module Kho."""
    from app.modules.quan_ly_kho.models import Product, StockMove

    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()

    # Lấy tất cả sản phẩm
    products = session.exec(
        __import__('sqlmodel').select(Product).order_by(Product.sku)
    ).all()

    result = []
    for p in products:
        # Nhập trong kỳ
        moves = session.exec(
            __import__('sqlmodel').select(StockMove)
            .where(StockMove.product_id == p.id)
            .where(StockMove.created_at >= datetime.combine(df, datetime.min.time(), tzinfo=timezone.utc))
            .where(StockMove.created_at <= datetime.combine(dt, datetime.max.time(), tzinfo=timezone.utc))
            .order_by(StockMove.created_at)
        ).all()

        if not moves:
            continue

        for m in moves:
            result.append({
                "date": m.created_at.date(),
                "product": p,
                "code": m.code if hasattr(m, 'code') else f"#{m.id}",
                "diary": m.note or ("Nhập kho" if m.move_type == "IN" else "Xuất kho"),
                "move_type": m.move_type,
                "quantity": m.quantity,
                "unit_price": m.unit_price,
                "amount": m.quantity * m.unit_price,
            })

    return templates.TemplateResponse(
        request=request, name="ke_toan/report_s2d.html",
        context={
            "rows": result,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
        },
    )


@router.get("/reports/s2e")
def report_s2e(
    request: Request,
    cash_account_id: str = "",
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()

    accounts = services.get_all_cash_accounts(session, only_active=True)
    cid = _to_int_or_none(cash_account_id)

    data = None
    if cid:
        data = services.report_s2e_cash_detail(session, cid, df, dt)

    return templates.TemplateResponse(
        request=request, name="ke_toan/report_s2e.html",
        context={
            "accounts": accounts,
            "selected_id": cid,
            "data": data,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
        },
    )


@router.get("/reports/s3a")
def report_s3a(
    request: Request,
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    """Sổ theo dõi nghĩa vụ thuế khác (S3a-HKD) — lọc phiếu chi có category=THUE."""
    from app.modules.ke_toan.models import Voucher

    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()

    vouchers = session.exec(
        __import__('sqlmodel').select(Voucher)
        .where(Voucher.voucher_type == "PAYMENT")
        .where(Voucher.category == "THUE")
        .where(Voucher.voucher_date >= df)
        .where(Voucher.voucher_date <= dt)
        .order_by(Voucher.voucher_date)
    ).all()

    total = sum(v.amount for v in vouchers)

    return templates.TemplateResponse(
        request=request, name="ke_toan/report_s3a.html",
        context={
            "vouchers": vouchers, "total": total,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
        },
    )


@router.get("/reports/tax")
def report_tax(
    request: Request,
    date_from: str = "", date_to: str = "",
    session: Session = Depends(get_session),
):
    df = _to_date(date_from) or _default_date_range()[0]
    dt = _to_date(date_to) or date.today()
    summary = services.report_tax_summary(session, df, dt)
    profile = services.get_hkd_profile(session)
    return templates.TemplateResponse(
        request=request, name="ke_toan/report_tax.html",
        context={
            "summary": summary, "profile": profile,
            "date_from": df.strftime("%Y-%m-%d"),
            "date_to": dt.strftime("%Y-%m-%d"),
        },
    )


@router.get("/reports/debt")
def report_debt(request: Request, session: Session = Depends(get_session)):
    data = services.report_debt_summary(session)
    context = dict(data)
    context["now"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    return templates.TemplateResponse(
        request=request, name="ke_toan/report_debt.html",
        context=context,
    )


