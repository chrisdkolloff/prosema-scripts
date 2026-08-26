"""FastAPI application: lifespan, middleware, and routers."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from app.auth import callback, login, logout
from app.config import settings
from app.jobs import worker_loop
from app.routes import batches as batches_routes
from app.routes import einstellungen as einstellungen_routes
from app.routes import gruppen as gruppen_routes
from app.routes import jobs as jobs_routes
from app.routes import pages as pages_routes
from app.routes import snapshots as snapshots_routes
from app.routes import supply_exports as supply_exports_routes
from app.routes import tools as tools_routes
from app.version_info import load_version_info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))
_version_info = load_version_info()
templates.env.globals["app_version"] = _version_info.version

_worker_stop = threading.Event()
_worker_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _worker_thread
    _worker_stop.clear()
    _worker_thread = threading.Thread(
        target=worker_loop,
        args=(_worker_stop,),
        name="job-worker",
        daemon=True,
    )
    _worker_thread.start()
    yield
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=8)


app = FastAPI(title="PROSEMA", lifespan=lifespan)
app.state.templates = templates
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=(settings.environment == "production"),
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")
app.include_router(pages_routes.router)
app.include_router(jobs_routes.router)
app.include_router(gruppen_routes.router)
app.include_router(einstellungen_routes.router)
app.include_router(tools_routes.router)
app.include_router(batches_routes.router)
app.include_router(snapshots_routes.router)
app.include_router(supply_exports_routes.router)
app.add_api_route("/auth/login", login, methods=["GET"])
app.add_api_route("/auth/callback", callback, methods=["GET"])
app.add_api_route("/auth/logout", logout, methods=["GET"])


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if exc.status_code in {301, 302, 303, 307, 308}:
        location = exc.headers.get("Location") if exc.headers else None
        if location:
            return RedirectResponse(url=location, status_code=exc.status_code)
    if exc.status_code == 403:
        user = request.session.get("user") if hasattr(request, "session") else None
        return templates.TemplateResponse(
            request,
            "forbidden.html",
            {"user": user},
            status_code=403,
        )
    return HTMLResponse(
        content=exc.detail if isinstance(exc.detail, str) else "Fehler",
        status_code=exc.status_code,
    )
