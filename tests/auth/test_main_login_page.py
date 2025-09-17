"""
Tests for the main.py login_page endpoint
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from borgitory.models.database import User


@pytest.fixture
async def authenticated_user(test_db: Session, async_client: AsyncClient):
    """Create a real user and return auth cookie for testing."""
    test_user = User(username="loginpagetest")
    test_user.set_password("testpass123")
    test_db.add(test_user)
    test_db.commit()
    test_db.refresh(test_user)

    # Login to get auth cookie
    response = await async_client.post(
        "/auth/login",
        data={"username": "loginpagetest", "password": "testpass123"},
    )
    assert response.status_code == 200
    auth_token = response.cookies["auth_token"]

    # Set the cookie for future requests
    async_client.cookies.set("auth_token", auth_token)

    yield test_user


class TestLoginPageEndpoint:
    """Test class for login_page endpoint in main.py."""

    @pytest.mark.asyncio
    async def test_login_page_no_user_no_next_param(
        self, async_client: AsyncClient
    ) -> None:
        """Test login page with no authenticated user and no next parameter."""
        response = await async_client.get("/login")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Borgitory" in response.text
        assert "BorgBackup Web Manager" in response.text
        # Should contain the auth form container
        assert "auth-form-container" in response.text
        # Should have default next parameter in HTMX call
        assert "/auth/check-users?next=/repositories" in response.text

    @pytest.mark.asyncio
    async def test_login_page_no_user_with_next_param(
        self, async_client: AsyncClient
    ) -> None:
        """Test login page with no authenticated user but with next parameter."""
        response = await async_client.get("/login?next=/backups")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Borgitory" in response.text
        # Should contain the next parameter in HTMX call
        assert "/auth/check-users?next=/backups" in response.text

    @pytest.mark.asyncio
    async def test_login_page_no_user_with_url_encoded_next(
        self, async_client: AsyncClient
    ) -> None:
        """Test login page with URL encoded next parameter."""
        response = await async_client.get("/login?next=%2Fcloud-sync")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        # Should properly handle URL encoded parameter
        assert "/auth/check-users?next=/cloud-sync" in response.text

    @pytest.mark.asyncio
    async def test_login_page_authenticated_user_redirects_default(
        self, async_client: AsyncClient, authenticated_user
    ) -> None:
        """Test login page with authenticated user redirects to default location."""
        response = await async_client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/repositories"

    @pytest.mark.asyncio
    async def test_login_page_authenticated_user_redirects_to_next(
        self, async_client: AsyncClient, authenticated_user
    ) -> None:
        """Test login page with authenticated user redirects to next parameter."""
        response = await async_client.get(
            "/login?next=/schedules", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/schedules"

    @pytest.mark.asyncio
    async def test_login_page_malicious_external_next_param_sanitized(
        self, async_client: AsyncClient
    ) -> None:
        """Test that external URLs in next parameter are sanitized."""
        response = await async_client.get("/login?next=https://evil.com/steal-data")
        assert response.status_code == 200
        # Should fall back to default /repositories for external URLs
        assert "/auth/check-users?next=/repositories" in response.text

    @pytest.mark.asyncio
    async def test_login_page_malicious_scheme_next_param_sanitized(
        self, async_client: AsyncClient
    ) -> None:
        """Test that URLs with schemes in next parameter are sanitized."""
        response = await async_client.get("/login?next=javascript:alert('xss')")
        assert response.status_code == 200
        # Should fall back to default /repositories for URLs with schemes
        assert "/auth/check-users?next=/repositories" in response.text

    @pytest.mark.asyncio
    async def test_login_page_backslash_in_next_param_cleaned(
        self, async_client: AsyncClient
    ) -> None:
        """Test that backslashes in next parameter are cleaned."""
        response = await async_client.get("/login?next=/archives\\..\\evil")
        assert response.status_code == 200
        # Should remove backslashes
        assert "/auth/check-users?next=/archives..evil" in response.text

    @pytest.mark.asyncio
    async def test_login_page_authenticated_user_with_malicious_next_redirects_safely(
        self, async_client: AsyncClient, authenticated_user
    ) -> None:
        """Test authenticated user with malicious next param redirects safely."""
        response = await async_client.get(
            "/login?next=https://evil.com", follow_redirects=False
        )
        assert response.status_code == 302
        # Should redirect to safe default instead of malicious URL
        assert response.headers["location"] == "/repositories"

    @pytest.mark.asyncio
    async def test_login_page_empty_next_param_uses_default(
        self, async_client: AsyncClient
    ) -> None:
        """Test login page with empty next parameter uses default."""
        response = await async_client.get("/login?next=")
        assert response.status_code == 200
        # Empty string gets passed through, not replaced with default
        assert "/auth/check-users?next=" in response.text

    @pytest.mark.asyncio
    async def test_login_page_valid_internal_next_param(
        self, async_client: AsyncClient
    ) -> None:
        """Test login page with valid internal next parameter."""
        response = await async_client.get("/login?next=/debug")
        assert response.status_code == 200
        # Should preserve valid internal URL
        assert "/auth/check-users?next=/debug" in response.text

    @pytest.mark.asyncio
    async def test_login_page_authenticated_user_preserves_valid_next(
        self, async_client: AsyncClient, authenticated_user
    ) -> None:
        """Test authenticated user with valid next parameter gets redirected correctly."""
        response = await async_client.get(
            "/login?next=/notifications", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/notifications"
