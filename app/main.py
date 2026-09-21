import os
from datetime import datetime

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="My Backend API")


class Item(BaseModel):
    name: str
    price: float


class NoteCreate(BaseModel):
    title: str
    content: str


class Note(NoteCreate):
    id: int
    created_at: datetime | None = None


def get_db_connection():
    return psycopg.connect(os.getenv("DATABASE_URL"))


@app.on_event("startup")
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/version")
def get_version():
    return {"version": "0.1.0"}


@app.post("/items")
def create_item(item: Item):
    return item


@app.get("/notes")
def get_notes():
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


@app.get("/note/{id}")
def get_note(id: int):
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


@app.post("/note")
def create_note(note: NoteCreate):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO notes (title, content) VALUES (%s, %s) RETURNING id, title, content, created_at",
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


@app.put("/note/{id}")
def update_note(id: int, note: NoteCreate):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notes SET title = %s, content = %s WHERE id = %s RETURNING id, title, content, created_at",
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


@app.delete("/note/{id}")
def delete_note(id: int):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE id = %s RETURNING id", (id,))
            deleted = cur.fetchone()
            conn.commit()

    if deleted is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return {"message": f"Note {id} deleted successfully"}