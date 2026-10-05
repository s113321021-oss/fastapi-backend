import os
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.requests import Request

load_dotenv()


def normalize_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    prefix = prefix.strip().rstrip("/")
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    if prefix == "/":
        return ""
    return prefix


PUBLIC_PREFIX = normalize_prefix(os.getenv("ROOT_PATH", "/s113321021"))
ROOT_PATH = PUBLIC_PREFIX
SERVERS = [{"url": ROOT_PATH}] if ROOT_PATH else []

app = FastAPI(
    title="My Backend API + Web App",
    root_path=ROOT_PATH,
    servers=SERVERS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    root_path_in_servers=True,
)


@app.middleware("http")
async def proxy_prefix_middleware(request: Request, call_next):
    forwarded_prefix = request.headers.get("x-forwarded-prefix") or request.headers.get("X-Forwarded-Prefix")
    effective_prefix = normalize_prefix(forwarded_prefix or ROOT_PATH)

    if effective_prefix:
        request.scope["root_path"] = effective_prefix
        raw_path = request.scope.get("path", "")
        if raw_path.startswith(effective_prefix):
            request.scope["path"] = raw_path[len(effective_prefix) :] or "/"

    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PUBLIC_ASSETS_DIR = STATIC_DIR / "assets"


@app.get("/static/{full_path:path}")
@app.get(f"{PUBLIC_PREFIX}/static/{{full_path:path}}")
async def serve_static_file(full_path: str):
    if not STATIC_DIR.exists():
        raise HTTPException(status_code=404, detail="Static directory not found")

    requested = (STATIC_DIR / full_path).resolve()
    if not str(requested).startswith(str(STATIC_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")

    if requested.is_file():
        return FileResponse(requested)

    raise HTTPException(status_code=404, detail="File not found")


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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg.connect(database_url)


@app.on_event("startup")
def init_db():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return

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


@app.get("/")
@app.get(f"{PUBLIC_PREFIX}/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "FastAPI backend is running. Add app/static/index.html for the web app."}


@app.get("/api/health")
@app.get(f"{PUBLIC_PREFIX}/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/version")
@app.get(f"{PUBLIC_PREFIX}/api/version")
def get_version():
    return {"version": "0.1.0"}


@app.post("/api/items")
@app.post(f"{PUBLIC_PREFIX}/api/items")
def create_item(item: Item):
    return item


@app.get("/api/notes")
@app.get(f"{PUBLIC_PREFIX}/api/notes")
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


@app.get("/api/note/{id}")
@app.get(f"{PUBLIC_PREFIX}/api/note/{{id}}")
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


@app.post("/api/note")
@app.post(f"{PUBLIC_PREFIX}/api/note")
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


@app.put("/api/note/{id}")
@app.put(f"{PUBLIC_PREFIX}/api/note/{{id}}")
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


@app.delete("/api/note/{id}")
@app.delete(f"{PUBLIC_PREFIX}/api/note/{{id}}")
def delete_note(id: int):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE id = %s RETURNING id", (id,))
            deleted = cur.fetchone()
            conn.commit()

    if deleted is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return {"message": f"Note {id} deleted successfully"}


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    protected_prefixes = ("docs", "redoc", "openapi", "static", "favicon.ico")
    if full_path.startswith(protected_prefixes):
        raise HTTPException(status_code=404, detail="Page not found")

    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Page not found")