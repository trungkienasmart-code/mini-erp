from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import TEMPLATES_DIR
from app.core.database import get_session
from app.modules.demo import services
from app.modules.demo.schemas import NoteCreate
from app.core.templates import templates
router = APIRouter(prefix="/demo", tags=["Demo"])


@router.get("/notes")
def note_list(request: Request, session: Session = Depends(get_session)):
    notes = services.get_all_notes(session)
    return templates.TemplateResponse(
        request=request,
        name="demo/note_list.html",
        context={"notes": notes},
    )

@router.post("/notes/create")
def note_create(
    title: str = Form(...),
    content: str = Form(""),
    session: Session = Depends(get_session),
):
    services.create_note(session, NoteCreate(title=title, content=content))
    return RedirectResponse(url="/demo/notes", status_code=303)

@router.post("/notes/{note_id}/delete")
def note_delete(note_id: int, session: Session = Depends(get_session)):
    services.delete_note(session, note_id)
    return RedirectResponse(url="/demo/notes", status_code=303)