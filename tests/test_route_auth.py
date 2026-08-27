"""Fail-closed: every non-public route must declare an auth dependency.

Protection is opt-in per route via ``Depends(require_user)`` /
``get_current_user``. A forgotten dependency leaves weclapp data reachable
without login. This test walks the route table only — no network or DB I/O.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.routing import APIRoute
from starlette.routing import Mount, Route

from app.auth import get_current_user, require_user
from app.config import settings
from app.main import app

PUBLIC_EXACT = {
    "/health",  # unauthenticated probe for App Service health check
    "/artikel",  # legacy 301 to /artikel-uebersicht; no data, target is protected
    "/einstellungen/weclapp",  # legacy 303 to /einstellungen; no data, target is protected
}
# OIDC handshake; vendored frontend assets.
PUBLIC_PREFIXES = ("/auth", "/static")

# OpenAPI UI — local/dev only. Disabled in production (see app/main.py).
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})

_AUTH_CALLABLES = frozenset({require_user, get_current_user})


def _is_public(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    if path in _DOCS_PATHS or path.startswith("/docs"):
        # Allowed only when docs are enabled (non-production).
        return settings.environment != "production"
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PUBLIC_PREFIXES)


def _dependant_calls(dependant) -> list:
    calls: list = []
    if dependant is None:
        return calls
    if dependant.call is not None:
        calls.append(dependant.call)
    for child in dependant.dependencies or []:
        calls.extend(_dependant_calls(child))
    return calls


def _route_has_auth(route: APIRoute, extra_calls: list | None = None) -> bool:
    calls = _dependant_calls(route.dependant)
    if extra_calls:
        calls.extend(extra_calls)
    return any(call in _AUTH_CALLABLES for call in calls)


def _mount_is_public(path: str) -> bool:
    normalised = path.rstrip("/") or path
    return any(
        normalised == prefix or normalised.startswith(prefix + "/")
        for prefix in PUBLIC_PREFIXES
    )


def _iter_api_routes() -> Iterator[tuple[APIRoute, list]]:
    """Yield ``(APIRoute, router-level dependency callables)`` from the app.

    FastAPI 0.141+ keeps ``include_router`` targets as ``_IncludedRouter``
    wrappers rather than flattening into ``app.routes``. Walk those so a
    forgotten auth dependency is still visible. Router-level
    ``dependencies=[...]`` from ``include_router`` / ``APIRouter`` live on
    the include context and are passed alongside each route.
    """
    for top in app.routes:
        if isinstance(top, APIRoute):
            yield top, []
            continue
        if type(top).__name__ != "_IncludedRouter":
            continue
        include_deps = list(top.include_context.dependencies or [])
        extra_calls = [
            dep.dependency
            for dep in include_deps
            if getattr(dep, "dependency", None) is not None
        ]
        for route in top.original_router.routes:
            if not isinstance(route, APIRoute):
                continue
            yield route, extra_calls


def test_every_route_is_authenticated_or_explicitly_public():
    unprotected: list[str] = []
    docs_in_production: list[str] = []
    nested_auth_seen = False

    for top in app.routes:
        if isinstance(top, Mount):
            assert _mount_is_public(top.path), (
                f"Mount {top.path} has no dependant and is not under "
                f"PUBLIC_PREFIXES. Add the path to PUBLIC_PREFIXES in this "
                f"file with a comment explaining why it is public."
            )
            continue

        # Docs are starlette.routing.Route, not APIRoute — do not skip silently.
        if isinstance(top, Route) and not isinstance(top, APIRoute):
            path = top.path
            methods = sorted(m for m in (top.methods or {"GET"}) if m != "HEAD")
            is_docs = path in _DOCS_PATHS or path.startswith("/docs")
            if is_docs and settings.environment == "production":
                for method in methods:
                    docs_in_production.append(f"{method} {path}")
            elif not _is_public(path):
                for method in methods:
                    unprotected.append(f"{method} {path}")

    for route, extra_calls in _iter_api_routes():
        methods = sorted(m for m in (route.methods or set()) if m != "HEAD")
        path = route.path
        if _is_public(path):
            continue

        if not _route_has_auth(route, extra_calls):
            for method in methods:
                unprotected.append(f"{method} {path}")
            continue

        calls = _dependant_calls(route.dependant)
        calls.extend(extra_calls)
        if require_user in calls and get_current_user in calls:
            nested_auth_seen = True

    errors: list[str] = []
    if docs_in_production:
        errors.append(
            "OpenAPI docs routes must not be registered in production: "
            + ", ".join(docs_in_production)
            + ". Set docs_url=None, redoc_url=None, openapi_url=None on FastAPI."
        )
    if unprotected:
        errors.append(
            "; ".join(
                f"{item} has no auth dependency. Add Depends(require_user), or add "
                f"the path to PUBLIC_EXACT in this file with a comment explaining "
                f"why it is public."
                for item in unprotected
            )
        )
    if errors:
        raise AssertionError(" ".join(errors))

    assert nested_auth_seen, (
        "Expected at least one route whose dependency tree includes both "
        "require_user and get_current_user (nested Depends)."
    )
