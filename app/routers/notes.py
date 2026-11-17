from fastapi import APIRouter, HTTPException

from app.core.db import get_db_connection
from app.models.main import NoteCreate

router = APIRouter(prefix="/api")


@router.get("/notes")
def get_notes() -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, content, created_at FROM notes ORDER BY id ASC"
            )
            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


@router.get("/note/{id}")
def get_note(id: int) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, content, created_at FROM notes WHERE id = %s",
                (id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return {
        "id": row[0],
        "title": row[1],
        "content": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
    }


@router.post("/note")
def create_note(note: NoteCreate) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO notes (title, content) VALUES (%s, %s) "
                "RETURNING id, title, content, created_at",
                (note.title, note.content),
            )
            row = cur.fetchone()
            conn.commit()

    return {
        "id": row[0],
        "title": row[1],
        "content": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
    }


@router.put("/note/{id}")
def update_note(id: int, note: NoteCreate) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notes SET title = %s, content = %s WHERE id = %s "
                "RETURNING id, title, content, created_at",
                (note.title, note.content, id),
            )
            row = cur.fetchone()
            conn.commit()

    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return {
        "id": row[0],
        "title": row[1],
        "content": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
    }


@router.delete("/note/{id}")
def delete_note(id: int) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE id = %s RETURNING id", (id,))
            deleted = cur.fetchone()
            conn.commit()

    if deleted is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return {"message": f"Note {id} deleted successfully"}
