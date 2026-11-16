"""
Guard against accidentally shipping unauthenticated endpoints.

Every route must depend on ``get_current_user`` unless it is listed in
``PUBLIC_ROUTES``. Adding a route to that list should be a deliberate decision:
public routes must not return user data or trigger side effects.
"""

from typing import Any, Iterable, Iterator, Sequence, Tuple

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from borgitory.api.auth import get_current_user
from borgitory.main import app

PUBLIC_ROUTES = {
    # Login / registration flow
    ("GET", "/"),
    ("GET", "/login"),
    ("GET", "/{tab_name}"),  # handler redirects to /login when unauthenticated
    ("GET", "/health"),
    ("GET", "/auth/check-users"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    # Stateless UI fragments (static markup, no data access)
    ("GET", "/api/repositories/modal/close"),
    ("GET", "/api/schedules/hooks/close-modal"),
    ("GET", "/api/schedules/patterns/close-modal"),
    ("POST", "/api/schedules/patterns/add-pattern-field"),
    ("POST", "/api/schedules/patterns/move-pattern"),
    ("POST", "/api/schedules/patterns/remove-pattern-field"),
    ("POST", "/api/schedules/patterns/patterns-modal"),
    ("POST", "/api/schedules/patterns/save-patterns"),
    ("POST", "/api/schedules/patterns/validate-all-patterns"),
    ("GET", "/api/cloud-sync/s3/providers"),
    ("GET", "/api/cloud-sync/s3/regions"),
    ("GET", "/api/cloud-sync/s3/storage-classes"),
    ("GET", "/api/cloud-sync/s3/endpoint-field"),
    ("GET", "/api/shared/notification"),
    ("GET", "/api/shared/notification-remove"),
}


def _requires_auth(dependant: Dependant) -> bool:
    if dependant.call is get_current_user:
        return True
    return any(_requires_auth(d) for d in dependant.dependencies)


def _iter_routes(
    routes: Iterable[Any], prefix: str = "", extra_deps: Sequence[Any] = ()
) -> Iterator[Tuple[APIRoute, str, Sequence[Any]]]:
    """Walk app routes, descending into included routers (lazy or flattened)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route, prefix + route.path, extra_deps
        elif hasattr(route, "original_router"):
            ctx = route.include_context
            yield from _iter_routes(
                route.original_router.routes,
                prefix + (ctx.prefix or ""),
                tuple(extra_deps) + tuple(ctx.dependencies or ()),
            )


def _all_routes() -> list[tuple[str, str, bool]]:
    found = []
    for route, path, extra_deps in _iter_routes(app.routes):
        deps = list(extra_deps) + list(route.dependencies)
        authed = _requires_auth(route.dependant) or any(
            getattr(d, "dependency", None) is get_current_user for d in deps
        )
        for method in route.methods:
            found.append((method, path, authed))
    return found


def test_route_walker_finds_routes() -> None:
    paths = {path for _, path, _ in _all_routes()}
    assert "/api/debug/info" in paths
    assert "/api/repositories/" in paths or any(
        p.startswith("/api/repositories") for p in paths
    )


def test_all_non_public_routes_require_auth() -> None:
    unauthenticated = sorted(
        (method, path)
        for method, path, authed in _all_routes()
        if not authed and (method, path) not in PUBLIC_ROUTES
    )
    assert unauthenticated == [], (
        "These routes have no get_current_user dependency. Add authentication, "
        "or add them to PUBLIC_ROUTES if they are intentionally public: "
        f"{unauthenticated}"
    )


def test_debug_endpoints_reject_anonymous_requests() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)  # no `with`: don't run the app lifespan
    assert client.get("/api/debug/info").status_code == 401
    assert client.get("/api/debug/html").status_code == 401


def test_health_endpoint_is_public_and_minimal() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
