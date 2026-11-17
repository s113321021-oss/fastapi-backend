import os
import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.requests import Request

from app.core.db import get_db_connection, initialize_tables
from app.routers.auth import router as auth_router
from app.routers.notes import router as notes_router
from app.routers.system import router as system_router
from app.routers.user_access import router as user_access_router

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
app.include_router(user_access_router)
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(system_router)


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

cors_origins = [
    origin
    for origin in json.loads(os.getenv("CORS_ORIGINS", "[]"))
    if origin != "*"
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
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


@app.on_event("startup")
def init_db():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return

    with get_db_connection() as conn:
        initialize_tables(conn)


@app.get("/")
@app.get(f"{PUBLIC_PREFIX}/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "FastAPI backend is running. Add app/static/index.html for the web app."}


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    protected_prefixes = ("docs", "redoc", "openapi", "static", "favicon.ico")
    if (
        full_path == "api"
        or full_path.startswith("api/")
        or full_path.startswith(protected_prefixes)
    ):
        raise HTTPException(status_code=404, detail="Page not found")

    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Page not found")