import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request

from app.core.db import get_db_connection, initialize_tables
from app.core.password_auth import trust_proxy_headers
from app.core.rate_limit import enforce_rate_limit
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
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").strip().lower() in {"1", "true", "yes"}

app = FastAPI(
    title="My Backend API + Web App",
    root_path=ROOT_PATH,
    servers=SERVERS,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
    root_path_in_servers=True,
)
app.include_router(user_access_router)
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(system_router)


@app.middleware("http")
async def proxy_prefix_middleware(request: Request, call_next):
    forwarded_prefix = ""
    if trust_proxy_headers():
        forwarded_prefix = request.headers.get("x-forwarded-prefix") or request.headers.get(
            "X-Forwarded-Prefix"
        )
    effective_prefix = normalize_prefix(forwarded_prefix or ROOT_PATH)

    if effective_prefix:
        request.scope["root_path"] = effective_prefix
        raw_path = request.scope.get("path", "")
        if raw_path.startswith(effective_prefix):
            request.scope["path"] = raw_path[len(effective_prefix) :] or "/"

    return await call_next(request)

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
SPA_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


def _csrf_cookie_secure() -> bool:
    secure_setting = os.getenv("SESSION_COOKIE_SECURE", "").strip().lower()
    if secure_setting:
        return secure_setting not in {"false", "0", "no"}
    return True


def _rate_limit_bucket(path: str, method: str) -> tuple[str, int, int] | None:
    normalized = path.rstrip("/")
    if not ("/api/" in path or normalized.endswith("/api")):
        return None
    if normalized.endswith("/api/auth/login") and method == "POST":
        return ("auth-login", 10, 60)
    if normalized.endswith("/api/auth/register") and method == "POST":
        return ("auth-register", 10, 60)
    if normalized.endswith("/api/check-in/qr/lookup") and method == "POST":
        return ("qr-lookup", 30, 60)
    if "/api/check-in/registrations/" in path and normalized.endswith("/confirm") and method == "POST":
        return ("checkin-confirm", 30, 60)
    if "/qr" in normalized and method == "GET":
        return ("qr-read", 60, 60)
    return ("api", 120, 60)


@app.middleware("http")
async def csrf_protect_middleware(request: Request, call_next):
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    path = request.url.path
    method = request.method.upper()
    is_api_path = "/api/" in path or path.rstrip("/").endswith("/api")

    bucket = _rate_limit_bucket(path, method)
    if bucket is not None:
        try:
            enforce_rate_limit(request, *bucket)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    if method not in CSRF_SAFE_METHODS and is_api_path:
        header_token = request.headers.get(CSRF_HEADER_NAME, "")
        if not csrf_cookie or not header_token or not secrets.compare_digest(csrf_cookie, header_token):
            return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid."})

    response = await call_next(request)
    if not csrf_cookie:
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=secrets.token_urlsafe(32),
            httponly=False,
            secure=_csrf_cookie_secure(),
            samesite="lax",
            path="/",
        )
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)

    path = request.url.path.rstrip("/")
    if path.endswith("/docs") or path.endswith("/redoc") or path.endswith("/openapi.json"):
        response.headers.setdefault("Content-Security-Policy", DOCS_CSP)
    else:
        response.headers.setdefault("Content-Security-Policy", SPA_CSP)

    if _csrf_cookie_secure():
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


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
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PUBLIC_ASSETS_DIR = STATIC_DIR / "assets"


@app.get("/static/{full_path:path}")
@app.get(f"{PUBLIC_PREFIX}/static/{{full_path:path}}")
async def serve_static_file(full_path: str):
    if not STATIC_DIR.exists():
        raise HTTPException(status_code=404, detail="Static directory not found")

    static_root = STATIC_DIR.resolve()
    requested = (STATIC_DIR / full_path).resolve()
    if not requested.is_relative_to(static_root):
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