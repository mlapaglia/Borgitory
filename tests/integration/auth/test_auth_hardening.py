"""Integration tests for session storage, login throttling and CSRF."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.api.auth import login_throttle
from borgitory.models.database import UserSession
from borgitory.utils.web_security import hash_session_token


async def _login(client: AsyncClient, password: str = "test_password") -> int:
    resp = await client.post(
        "/auth/login", data={"username": "test_user", "password": password}
    )
    return resp.status_code


async def test_session_token_stored_hashed(
    async_client_without_auth: AsyncClient, test_db: AsyncSession
) -> None:
    resp = await async_client_without_auth.post(
        "/auth/login", data={"username": "test_user", "password": "test_password"}
    )
    cookie = resp.cookies["auth_token"]

    stored = (await test_db.execute(select(UserSession.session_token))).scalars().all()
    assert cookie not in stored
    assert hash_session_token(cookie) in stored


async def test_login_throttled_after_repeated_failures(
    async_client_without_auth: AsyncClient,
) -> None:
    for _ in range(login_throttle.max_failures):
        assert await _login(async_client_without_auth, "wrong") == 401

    # Even the correct password is refused while throttled
    resp = await async_client_without_auth.post(
        "/auth/login", data={"username": "test_user", "password": "test_password"}
    )
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


async def test_successful_login_resets_failure_count(
    async_client_without_auth: AsyncClient,
) -> None:
    for _ in range(login_throttle.max_failures - 1):
        await _login(async_client_without_auth, "wrong")
    assert await _login(async_client_without_auth) == 200
    assert await _login(async_client_without_auth, "wrong") == 401


async def test_login_rejects_external_redirect(
    async_client_without_auth: AsyncClient,
) -> None:
    resp = await async_client_without_auth.post(
        "/auth/login",
        data={
            "username": "test_user",
            "password": "test_password",
            "next": "https://evil.example/phish",
        },
    )
    assert resp.headers["HX-Redirect"] == "/repositories"


async def test_cross_site_post_rejected(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert resp.status_code == 403
