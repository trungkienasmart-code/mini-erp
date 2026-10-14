# app/modules/backup/router.py
from urllib.parse import quote
from datetime import datetime, date

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, StreamingResponse, FileResponse
from sqlmodel import Session

from app.core.templates import templates
from app.core.database import get_session
from app.modules.auth.dependencies import require_login
from app.modules.backup import services

router = APIRouter(prefix="/backup", tags=["Backup"])


# ============================================================
# HELPERS
# ============================================================
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except ValueError:
        return None


def _redirect_with_msg(url: str, kind: str, msg: str):
    return RedirectResponse(url=f"{url}?{kind}={quote(msg)}", status_code=303)


# ============================================================
# TRANG CHÍNH — SAO LƯU & PHỤC HỒI
# ============================================================
@router.get("/")
def backup_home(
    request: Request,
    user=Depends(require_login),
):
    backups = services.list_backups()
    status = services.get_backup_status()
    stats = services.get_backup_stats()

    return templates.TemplateResponse(
        request=request,
        name="backup/index.html",
        context={
            "user": user,
            "backups": backups,
            "status": status,
            "stats": stats,
            "active_tab": "backup",
        },
    )


@router.post("/create")
def backup_create(
    request: Request,
    note: str = Form(""),
    user=Depends(require_login),
):
    path, msg = services.create_backup(note=note, user_id=user.id)

    # Audit log
    if path:
        from sqlmodel import Session
        from app.core.database import engine
        from app.modules.auth.services import write_audit
        with Session(engine) as s:
            write_audit(
                s, user.id, "BACKUP", "system", None,
                description=f"Tạo backup: {path.name}",
                ip=request.client.host if request.client else "",
            )
            s.commit()

    return _redirect_with_msg(
        "/backup/",
        "success" if path else "error",
        msg,
    )


@router.post("/{backup_name}/delete")
def backup_delete(
    backup_name: str,
    request: Request,
    user=Depends(require_login),
):
    ok, msg = services.delete_backup(backup_name)
    return _redirect_with_msg(
        "/backup/",
        "success" if ok else "error",
        msg,
    )


@router.post("/{backup_name}/restore")
def backup_restore(
    backup_name: str,
    request: Request,
    user=Depends(require_login),
):
    ok, msg = services.restore_backup(backup_name)

    # Audit log
    if ok:
        from sqlmodel import Session
        from app.core.database import engine
        from app.modules.auth.services import write_audit
        with Session(engine) as s:
            write_audit(
                s, user.id, "RESTORE", "system", None,
                description=f"Phục hồi từ backup: {backup_name}",
                ip=request.client.host if request.client else "",
            )
            s.commit()

    return _redirect_with_msg(
        "/backup/",
        "success" if ok else "error",
        msg,
    )


@router.get("/{backup_name}/download")
def backup_download(
    backup_name: str,
    user=Depends(require_login),
):
    """Tải file backup về máy."""
    if ".." in backup_name or "/" in backup_name or "\\" in backup_name:
        return _redirect_with_msg("/backup/", "error", "Tên file không hợp lệ")

    from pathlib import Path
    path = services.BACKUP_DIR / backup_name
    if not path.exists():
        return _redirect_with_msg("/backup/", "error", "File không tồn tại")

    return FileResponse(
        path=str(path),
        media_type="application/zip",
        filename=backup_name,
    )


# ============================================================
# API — Trạng thái backup (cho badge nhắc nhở)
# ============================================================
@router.get("/api/status")
def backup_status_api(
    user=Depends(require_login),
):
    return services.get_backup_status()


# ============================================================
# EXPORT EXCEL
# ============================================================
@router.get("/export")
def export_page(
    request: Request,
    user=Depends(require_login),
):
    return templates.TemplateResponse(
        request=request,
        name="backup/export.html",
        context={"user": user, "active_tab": "export"},
    )


@router.get("/export/products")
def export_products(
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    data, msg = services.export_products_excel(session)
    if not data:
        return _redirect_with_msg("/backup/export", "error", msg)

    filename = f"san_pham_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/customers")
def export_customers(
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    data, msg = services.export_customers_excel(session)
    if not data:
        return _redirect_with_msg("/backup/export", "error", msg)

    filename = f"khach_hang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/suppliers")
def export_suppliers(
    user=Depends(require_login),
    session: Session = Depends(get_session),
):
    data, msg = services.export_suppliers_excel(session)
    if not data:
        return _redirect_with_msg("/backup/export", "error", msg)

    filename = f"nha_cung_cap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/orders")
def export_orders(
    user=Depends(require_login),
    session: Session = Depends(get_session),
    date_from: str = "",
    date_to: str = "",
):
    df = _to_date(date_from)
    dt = _to_date(date_to)

    data, msg = services.export_orders_excel(session, date_from=df, date_to=dt)
    if not data:
        return _redirect_with_msg("/backup/export", "error", msg)

    filename = f"don_ban_hang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    