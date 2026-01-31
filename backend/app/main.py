"""
ApexAurum Cloud - Main FastAPI Application

The cloud-native version of ApexAurum.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import init_db, close_db
from app.rate_limit import limiter
from app.api.v1 import router as api_v1_router
from app.tools import register_all_tools

settings = get_settings()


def init_vault():
    """Initialize The Vault storage directory."""
    from pathlib import Path
    import os

    vault_path = Path(settings.vault_path)
    users_path = vault_path / "users"

    print(f"Initializing Vault at: {vault_path}")
    print(f"  - Path exists: {vault_path.exists()}")
    print(f"  - Is writable: {os.access(vault_path, os.W_OK) if vault_path.exists() else 'N/A'}")

    try:
        users_path.mkdir(parents=True, exist_ok=True)
        print(f"  - Users directory ready: {users_path}")

        # Test write permission
        test_file = users_path / ".vault_test"
        test_file.write_text("ok")
        test_file.unlink()
        print("  - Write test: PASSED")
    except PermissionError as e:
        print(f"  - ERROR: Permission denied - {e}")
        print("  - TIP: Set RAILWAY_RUN_UID=0 in Railway env vars")
    except Exception as e:
        print(f"  - ERROR: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("=" * 50)
    print("ApexAurum Cloud v113 - Error Tracking")
    print("=" * 50)

    # Import all models before database init to ensure SQLAlchemy
    # can resolve all relationship string references
    from app import models  # noqa: F401
    print("Models loaded")

    await init_db()
    print("Database initialized")

    # Initialize Tool Registry
    register_all_tools()
    from app.tools import registry
    print(f"Tool registry: {registry.tool_count} tools registered")

    # Initialize Vault storage
    init_vault()

    # Auto-purge old error logs (GDPR compliance)
    try:
        from app.database import get_db_context
        from app.services.error_tracking import purge_old_errors
        async with get_db_context() as db:
            purged = await purge_old_errors(db)
            if purged > 0:
                print(f"Error log purge: removed {purged} old entries")
            else:
                print("Error log purge: no old entries")
    except Exception as e:
        print(f"Error log purge skipped: {e}")

    # Auto-promote initial admin from env var (or auto-create if missing)
    import os
    initial_admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "admin@apexaurum.no")
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not admin_password:
        import secrets
        admin_password = secrets.token_urlsafe(16)
        print(f"WARNING: No INITIAL_ADMIN_PASSWORD set. Generated: {admin_password}")
        print("Set INITIAL_ADMIN_PASSWORD env var for a fixed password.")
    print(f"Admin setup: target={initial_admin_email}")
    if initial_admin_email:
        try:
            from sqlalchemy import select
            from app.database import get_session_factory
            from app.models.user import User
            from app.auth import hash_password
            session_factory = get_session_factory()
            async with session_factory() as db:
                user = await db.scalar(select(User).where(User.email == initial_admin_email))
                if user and not user.is_admin:
                    user.is_admin = True
                    user.password_hash = hash_password(admin_password)
                    await db.commit()
                    print(f"Auto-promoted {initial_admin_email} to admin (password reset)")
                elif user and user.is_admin:
                    print(f"Admin already set: {initial_admin_email}")
                elif not user:
                    admin_user = User(
                        email=initial_admin_email,
                        password_hash=hash_password(admin_password),
                        display_name="Admin",
                        is_admin=True,
                    )
                    db.add(admin_user)
                    await db.commit()
                    print(f"Auto-created admin user: {initial_admin_email}")
        except Exception as e:
            import traceback
            print(f"Admin auto-setup error: {e}")
            traceback.print_exc()

    yield

    # Shutdown
    print("Shutting down...")
    await close_db()
    print("Database closed")


# Create FastAPI app
app = FastAPI(
    title="ApexAurum Cloud",
    description="""
    Production-grade AI interface with multi-agent orchestration,
    persistent memory, and 140+ integrated tools.

    ## Features

    - **Chat**: Stream responses from Claude with tool execution
    - **Agents**: Spawn background agents for complex tasks
    - **Village**: Multi-agent shared memory with convergence detection
    - **Tools**: 140+ tools for files, code, web, music, and more
    - **Music**: AI music generation via Suno

    ## Authentication

    All endpoints require JWT Bearer authentication except `/health` and `/auth/*`.
    """,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter


# Error tracking middleware
@app.middleware("http")
async def error_tracking_middleware(request: Request, call_next):
    """Track HTTP errors and unhandled exceptions for the admin dashboard."""
    import time as _time
    start = _time.time()

    try:
        response = await call_next(request)
        elapsed_ms = (_time.time() - start) * 1000

        # Log 5xx responses
        if response.status_code >= 500:
            try:
                from app.database import get_db_context
                from app.services.error_tracking import log_error

                # Extract user_id from JWT without DB hit
                user_id = None
                auth_header = request.headers.get("authorization", "")
                if auth_header.startswith("Bearer "):
                    try:
                        import jwt
                        token = auth_header[7:]
                        payload = jwt.decode(token, options={"verify_signature": False})
                        user_id = payload.get("sub")
                    except Exception:
                        pass

                async with get_db_context() as db:
                    await log_error(
                        db=db,
                        category="http_error",
                        error_type=f"HTTP_{response.status_code}",
                        message=f"{request.method} {request.url.path} returned {response.status_code}",
                        severity="error",
                        endpoint=str(request.url.path)[:300],
                        http_method=request.method,
                        status_code=response.status_code,
                        response_time_ms=elapsed_ms,
                        user_id=user_id,
                    )
            except Exception:
                pass  # Never break the response

        return response

    except Exception as exc:
        elapsed_ms = (_time.time() - start) * 1000

        # Log unhandled exception
        try:
            import traceback as _tb
            from app.database import get_db_context
            from app.services.error_tracking import log_error

            user_id = None
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    import jwt
                    token = auth_header[7:]
                    payload = jwt.decode(token, options={"verify_signature": False})
                    user_id = payload.get("sub")
                except Exception:
                    pass

            async with get_db_context() as db:
                await log_error(
                    db=db,
                    category="backend_exception",
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                    severity="critical",
                    stacktrace=_tb.format_exc(),
                    endpoint=str(request.url.path)[:300],
                    http_method=request.method,
                    response_time_ms=elapsed_ms,
                    user_id=user_id,
                )
        except Exception:
            pass  # Never suppress the original exception

        raise


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Rate limit exceeded handler with CORS support."""
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded", "detail": str(exc.detail)},
        headers=get_cors_headers(request),
    )


# Admin panel (served from backend - no CORS needed)
@app.get("/admin", tags=["Admin"], include_in_schema=False)
@app.get("/admin/", tags=["Admin"], include_in_schema=False)
async def admin_panel():
    """Serve the admin dashboard HTML."""
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    admin_path = Path(__file__).parent.parent / "admin_static" / "index.html"
    if not admin_path.exists():
        # Docker path
        admin_path = Path("/app/admin_static/index.html")
    if admin_path.exists():
        return HTMLResponse(content=admin_path.read_text())
    return HTMLResponse(content="<h1>Admin panel not found</h1>", status_code=404)


# Health check (no auth required)
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers and deployment verification."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "build": "v113-error-tracking",
        "agents": {
            "native": 5,
            "pac": 4,
        },
        "tools": 68,  # 15 Tiers! Village Band + Nursery Apprentice Protocol!
        "features": [
            "streaming",
            "pac-mode",
            "export",
            "import",
            "custom-agents",
            "agent-memory",
            "branching",
            "model-selection",
            "vault",
            "cortex-diver",
            "code-execution",
            "content-search",
            "project-context",
            "rag-injection",
            "tool-registry",
            "tool-execution",
            "steel-browser",
            "neo-cortex",
            "neural-space-3d",
            "village-websocket",
            "village-gui",
            "village-isometric-3d",
            "task-tickers",
            "village-particles",
            "village-click-select",
            "multi-provider-llm",
            "billing-subscriptions",
            "billing-credits",
            "stripe-integration",
            "local-embeddings",
            "council-deliberation",
            "suno-music",
            "apexXuno-frontend",
            "suno-compiler",
            "midi-compose",
            "village-band",
            "council-ws-streaming",
            "multi-provider-byok",
            "file-attachments-vision",
            "nursery-data-garden",
            "nursery-training-forge",
            "nursery-model-cradle",
            "nursery-apprentice-protocol",
            "nursery-polish",
            "usage-counters",
            "tier-restructure",
            "feature-credit-packs",
            "legal-pages",
            "usage-warnings",
            "platform-grants",
            "apexpocket-device-auth",
            "apexpocket-cloud-api",
            "device-management",
            "error-tracking",
        ],
    }


# Root redirect to docs
@app.get("/", include_in_schema=False)
async def root():
    """Redirect to API documentation."""
    return JSONResponse(
        content={
            "message": "ApexAurum Cloud API",
            "docs": "/docs",
            "health": "/health",
        }
    )


# Mount API v1 router
app.include_router(api_v1_router, prefix="/api/v1")

# Mount WebSocket routers
from app.api.v1.village_ws import router as village_ws_router
from app.api.v1.council_ws import router as council_ws_router
app.include_router(village_ws_router, prefix="/ws")
app.include_router(council_ws_router, prefix="/ws")


# Exception handlers
from fastapi import HTTPException


def get_cors_headers(request):
    """Build CORS headers for error responses."""
    origin = request.headers.get("origin", "")
    if origin in settings.allowed_origins_list:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTPException handler with CORS support."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=get_cors_headers(request),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler with CORS support."""
    import logging
    logger = logging.getLogger(__name__)
    logger.exception(f"Unhandled exception: {exc}")

    if settings.debug:
        detail = str(exc)
        exc_type = exc.__class__.__name__
    else:
        detail = "An internal error occurred"
        exc_type = "InternalError"

    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": detail, "type": exc_type},
        headers=get_cors_headers(request),
    )
