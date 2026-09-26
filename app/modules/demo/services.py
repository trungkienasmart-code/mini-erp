from typing import List
from sqlmodel import Session, select
from app.modules.demo.models import Note
from app.modules.demo.schemas import NoteCreate

def get_all_notes(session: Session) -> List[Note]:
    return list(session.exec(select(Note).order_by(Note.created_at.desc())).all())

def create_note(session: Session, data: NoteCreate) -> Note:
    note = Note(**data.model_dump())
    session.add(note)
    session.commit()
    session.refresh(note)
    return note

def delete_note(session: Session, note_id: int) -> bool:
    note = session.get(Note, note_id)
    if not note:
        return False
    session.delete(note)
    session.commit()
    return True