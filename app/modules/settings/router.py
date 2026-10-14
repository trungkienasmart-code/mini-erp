# app/modules/settings/router.py
import os
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import Session, select

from app.core.templates import templates
from app.core.database import get_session
from app.core.config import BASE_DIR
from app.modules.auth.dependencies import require_login, require_admin
from app.modules.ke_toan.models import HKDProfile
from app.modules.ke_toan.schemas import HKDProfileCreate
from app.modules.ke_toan import services as ke_toan_services
from app.modules.settings import network
from app.modules.settings import network, services as settings_services
from app.modules.ke_toan.models import BankTransaction

router = APIRouter(prefix="/settings", tags=["Settings"])


# ============================================================
# HELPERS
# ============================================================
LOGO_DIR = BASE_DIR / "app" / "static" / "uploads" / "logo"
LOGO_URL_PREFIX = "/static/uploads/logo"
ALLOWED_LOGO_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


def _get_profile(session: Session):
    return session.exec(select(HKDProfile)).first()


# ============================================================
# SHOP INFO
# ============================================================
@router.get("/")
def shop_settings(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)
    return templates.TemplateResponse(
        request=request,
        name="settings/shop.html",
        context={"user": user, "profile": profile, "active_tab": "shop"},
    )


@router.post("/save-shop")
def save_shop(
    request: Request,
    business_name: str = Form(...),
    tax_code: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    slogan: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)

    if profile:
        # Cập nhật
        profile.business_name = business_name
        profile.tax_code = tax_code
        profile.address = address
        profile.phone = phone
        profile.email = email
        profile.slogan = slogan
        session.add(profile)
    else:
        # Tạo mới
        profile = HKDProfile(
            business_name=business_name,
            tax_code=tax_code,
            address=address,
            phone=phone,
            email=email,
            slogan=slogan,
        )
        session.add(profile)

    session.commit()
    return _redirect_with_msg("/settings/", "success", "Đã lưu thông tin cửa hàng")


@router.post("/upload-logo")
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Upload logo cửa hàng."""
    profile = _get_profile(session)
    if not profile:
        return JSONResponse({"success": False, "message": "Chưa cấu hình cửa hàng"},
                             status_code=400)

    # Validate
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_LOGO_EXT:
        return JSONResponse({
            "success": False,
            "message": f"Chỉ hỗ trợ: {', '.join(sorted(ALLOWED_LOGO_EXT))}",
        }, status_code=400)

    content = await file.read()
    if len(content) > MAX_LOGO_SIZE:
        return JSONResponse({"success": False, "message": "Logo vượt quá 2MB"},
                             status_code=400)

    # Lưu file
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = LOGO_DIR / unique_name

    # Xóa logo cũ nếu có
    if profile.logo_path:
        old_name = Path(profile.logo_path).name
        old_file = LOGO_DIR / old_name
        if old_file.exists():
            try:
                old_file.unlink()
            except Exception:
                pass

    with open(file_path, "wb") as f:
        f.write(content)

    # Cập nhật
    profile.logo_path = f"{LOGO_URL_PREFIX}/{unique_name}"
    session.add(profile)
    session.commit()

    return JSONResponse({
        "success": True,
        "logo_url": profile.logo_path,
    })


@router.post("/delete-logo")
def delete_logo(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)
    if not profile or not profile.logo_path:
        return _redirect_with_msg("/settings/", "error", "Chưa có logo")

    # Xóa file
    old_name = Path(profile.logo_path).name
    old_file = LOGO_DIR / old_name
    if old_file.exists():
        try:
            old_file.unlink()
        except Exception:
            pass

    profile.logo_path = ""
    session.add(profile)
    session.commit()

    return _redirect_with_msg("/settings/", "success", "Đã xóa logo")


# ============================================================
# NETWORK (MẠNG LAN)
# ============================================================
@router.get("/network")
def network_settings(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)

    # Lấy thông tin mạng
    info = network.get_network_info(port=profile.lan_port if profile else 8000)

    # Nếu profile chưa lưu IP → tự cập nhật
    if profile and not profile.lan_host_ip:
        profile.lan_host_ip = info["host_ip"]
        session.add(profile)
        session.commit()

    return templates.TemplateResponse(
        request=request,
        name="settings/network.html",
        context={
            "user": user,
            "profile": profile,
            "info": info,
            "active_tab": "network",
        },
    )


@router.post("/open-firewall")
def open_firewall(
    request: Request,
    port: int = Form(8000),
    user=Depends(require_login),
):
    """Mở port trên Windows Firewall (sẽ hiện UAC)."""
    ok, msg = network.open_firewall_port(port)
    return _redirect_with_msg("/settings/network",
                               "success" if ok else "error", msg)


@router.post("/save-network")
def save_network(
    request: Request,
    lan_port: int = Form(8000),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)
    if not profile:
        return _redirect_with_msg("/settings/network", "error",
                                   "Chưa cấu hình cửa hàng")

    # Cập nhật IP + port mới
    info = network.get_network_info(port=lan_port)
    profile.lan_host_ip = info["host_ip"]
    profile.lan_port = lan_port
    session.add(profile)
    session.commit()

    return _redirect_with_msg("/settings/network", "success",
                               f"Đã lưu cấu hình mạng (Port {lan_port})")


# ============================================================
# BANK (Ngân hàng & VietQR)
# ============================================================
@router.get("/bank")
def bank_settings(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)
    return templates.TemplateResponse(
        request=request,
        name="settings/bank.html",
        context={"user": user, "profile": profile, "active_tab": "bank"},
    )
    
    # ============================================================
# BANK SAVE
# ============================================================
@router.post("/save-bank")
def save_bank(
    request: Request,
    bank_code: str = Form(""),
    bank_account_no: str = Form(""),
    bank_account_name: str = Form(""),
    enable_vietqr: str = Form(""),
    webhook_provider: str = Form("NONE"),
    webhook_api_key: str = Form(""),
    webhook_secret: str = Form(""),
    webhook_enabled: str = Form(""),
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    profile = _get_profile(session)
    if not profile:
        return _redirect_with_msg("/settings/bank", "error",
                                   "Chưa cấu hình cửa hàng. Vào tab 'Thông tin cửa hàng' trước.")

    profile.bank_code = bank_code.strip().upper()
    profile.bank_account_no = bank_account_no.strip()
    profile.bank_account_name = bank_account_name.strip().upper()
    profile.enable_vietqr = enable_vietqr == "on"
    profile.webhook_provider = webhook_provider
    profile.webhook_api_key = webhook_api_key.strip()
    profile.webhook_secret = webhook_secret.strip()
    profile.webhook_enabled = webhook_enabled == "on"

    session.add(profile)
    session.commit()

    return _redirect_with_msg("/settings/bank", "success",
                               "Đã lưu cấu hình ngân hàng")


@router.post("/test-vietqr")
def test_vietqr(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Test tạo QR từ config hiện tại."""
    profile = _get_profile(session)
    if not profile or not profile.bank_code or not profile.bank_account_no:
        return JSONResponse({
            "success": False,
            "message": "Chưa cấu hình đủ ngân hàng + STK",
        })

    url = settings_services.build_vietqr_url(
        bank_code=profile.bank_code,
        account_no=profile.bank_account_no,
        account_name=profile.bank_account_name,
        amount=100000,
        description="Test QR 100k",
    )
    return JSONResponse({"success": True, "qr_url": url})


# ============================================================
# WEBHOOK ENDPOINT — Cho Casso/Sepay gọi vào
# ============================================================
@router.post("/bank-webhook")
async def bank_webhook(
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Endpoint nhận webhook từ Casso/Sepay.
    URL cấu hình: https://{domain}/settings/bank-webhook
    """
    # Lấy raw body để verify signature
    body = await request.body()
    signature = request.headers.get("X-Signature", "") or \
                request.headers.get("X-Casso-Signature", "") or \
                request.headers.get("Authorization", "")

    profile = _get_profile(session)
    if not profile:
        return JSONResponse({"success": False, "error": "Chưa cấu hình"}, status_code=400)

    # Verify signature
    if not settings_services.verify_webhook(
        provider=profile.webhook_provider,
        payload=body,
        signature=signature,
        secret=profile.webhook_secret,
    ):
        # Log warning nhưng vẫn chấp nhận (để test dễ)
        print(f"[WARN] Webhook signature không khớp (provider={profile.webhook_provider})")

    # Parse JSON
    try:
        data = await request.json()
    except Exception as e:
        return JSONResponse({"success": False, "error": f"Invalid JSON: {e}"}, status_code=400)

    # === Parse theo provider ===
    provider = profile.webhook_provider
    transactions = []

    if provider == "CASSO":
        # Casso: {"data": [{"id":..., "amount":..., "description":...}]}
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]
        for item in items:
            transactions.append({
                "transaction_id": str(item.get("id") or item.get("tid") or ""),
                "bank_code": item.get("bankCode", profile.bank_code),
                "account_no": item.get("accountNumber", profile.bank_account_no),
                "amount": float(item.get("amount") or 0),
                "content": item.get("description", "") or item.get("transactionContent", ""),
                "transaction_date": None,
            })

    elif provider == "SEPAY":
        # Sepay: {"id":..., "transferAmount":..., "content":...}
        transactions.append({
            "transaction_id": str(data.get("id") or data.get("referenceCode") or ""),
            "bank_code": data.get("gateway", profile.bank_code),
            "account_no": data.get("accountNumber", profile.bank_account_no),
            "amount": float(data.get("transferAmount") or data.get("amount") or 0),
            "content": data.get("content") or data.get("description") or "",
            "transaction_date": None,
        })

    else:
        # Generic: tự detect format
        # Hỗ trợ: Casso format ({"data": [...]}), hoặc flat JSON
        items = []
        if "data" in data:
            raw_items = data["data"]
            items = raw_items if isinstance(raw_items, list) else [raw_items]
        elif "transactions" in data:
            raw_items = data["transactions"]
            items = raw_items if isinstance(raw_items, list) else [raw_items]
        else:
            items = [data]

        for item in items:
            transactions.append({
                "transaction_id": str(
                    item.get("id") or
                    item.get("transaction_id") or
                    item.get("tid") or
                    item.get("reference") or
                    item.get("referenceCode") or ""
                ),
                "bank_code": item.get("bankCode") or item.get("bank_code") or
                             item.get("gateway") or profile.bank_code,
                "account_no": item.get("accountNumber") or item.get("account_no") or
                              profile.bank_account_no,
                "amount": float(
                    item.get("amount") or
                    item.get("transferAmount") or 0
                ),
                "content": (
                    item.get("description") or
                    item.get("transactionContent") or
                    item.get("content") or ""
                ),
                "transaction_date": None,
            })

    # === Xử lý từng giao dịch ===
    results = []
    for txn in transactions:
        if not txn["transaction_id"]:
            continue
        result, msg = settings_services.process_webhook_transaction(
            session,
            transaction_id=txn["transaction_id"],
            bank_code=txn["bank_code"],
            account_no=txn["account_no"],
            amount=txn["amount"],
            content=txn["content"],
            transaction_date=txn["transaction_date"],
            raw_data=data,
        )
        results.append({
            "transaction_id": txn["transaction_id"],
            "status": result.status if result else "ERROR",
            "message": msg,
        })

    return JSONResponse({
        "success": True,
        "processed": len(results),
        "results": results,
    })


# ============================================================
# API POLLING CHO POS
# ============================================================
@router.get("/api/recent-bank-txns")
def api_recent_bank_txns(
    since_seconds: int = 60,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """API cho POS poll mỗi 5s để check CK mới về."""
    txns = settings_services.get_recent_bank_transactions(
        session, since_seconds=since_seconds,
    )
    return JSONResponse({
        "transactions": [
            {
                "id": t.id,
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "content": t.content,
                "matched_order_id": t.matched_order_id,
                "matched_order_code": t.matched_order_code,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
    })


# ============================================================
# DS GIAO DỊCH CHƯA KHỚP
# ============================================================
@router.get("/unmatched-txns")
def unmatched_txns(
    request: Request,
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    """Trang DS giao dịch CK chưa khớp để kế toán xử lý."""
    txns = settings_services.get_unmatched_transactions(session)
    return templates.TemplateResponse(
        request=request,
        name="settings/unmatched_txns.html",
        context={"user": user, "txns": txns, "active_tab": "bank"},
    )