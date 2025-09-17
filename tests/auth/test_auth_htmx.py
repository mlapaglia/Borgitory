"""
Tests for auth HTMX functionality
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from borgitory.models.database import User


class TestAuthHTMX:
    """Test class for auth HTMX functionality."""

    @pytest.mark.asyncio
    async def test_register_htmx_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test registration via HTMX returns HTML template."""
        # Make HTMX request
        response = await async_client.post(
            "/auth/register",
            data={"username": "testuser", "password": "testpassword"},
            headers={"hx-request": "true"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check for success message
        assert "Registration successful! You can now log in." in response.text

        # Verify user was created in database
        user = test_db.query(User).filter(User.username == "testuser").first()
        assert user is not None
        assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_register_htmx_validation_error(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test registration validation error via HTMX."""
        # Make HTMX request with invalid data
        response = await async_client.post(
            "/auth/register",
            data={"username": "ab", "password": "123"},  # Too short
            headers={"hx-request": "true"},
        )

        assert response.status_code == 400
        assert "text/html" in response.headers["content-type"]

        # Check for error message
        assert "Username must be at least 3 characters" in response.text

    @pytest.mark.asyncio
    async def test_login_htmx_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test login via HTMX returns HTML template."""
        # Create a test user
        user = User(username="testuser")
        user.set_password("testpassword")
        test_db.add(user)
        test_db.commit()

        # Make HTMX request
        response = await async_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "testpassword"},
            headers={"hx-request": "true"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check for success message and HX-Redirect header
        assert "Login successful! Redirecting..." in response.text
        assert response.headers.get("HX-Redirect") == "/repositories"

    @pytest.mark.asyncio
    async def test_login_htmx_invalid_credentials(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test login with invalid credentials via HTMX."""
        # Make HTMX request with invalid credentials
        response = await async_client.post(
            "/auth/login",
            data={"username": "nonexistent", "password": "wrong"},
            headers={"hx-request": "true"},
        )

        assert response.status_code == 401
        assert "text/html" in response.headers["content-type"]

        # Check for error message
        assert "Invalid username or password" in response.text

    @pytest.mark.asyncio
    async def test_check_users_no_users_returns_register_form(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test check-users endpoint returns register form when no users exist."""
        response = await async_client.get("/auth/check-users")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Should return register form with welcome message
        assert "No users exist yet" in response.text
        assert "Create the first administrator account" in response.text
        assert 'id="register-form"' in response.text
        assert 'action="/auth/register"' in response.text

    @pytest.mark.asyncio
    async def test_check_users_with_users_returns_login_form(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test check-users endpoint returns login form when users exist."""
        # Create a test user
        user = User(username="existinguser")
        user.set_password("password123")
        test_db.add(user)
        test_db.commit()

        response = await async_client.get("/auth/check-users")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Should return login form
        assert 'id="login-form"' in response.text
        assert 'action="/auth/login"' in response.text
        assert "Remember me" in response.text
