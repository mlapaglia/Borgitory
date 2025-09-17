"""
Test for auth redirect flow - debugging the login redirect issue
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from borgitory.models.database import User


class TestAuthRedirectFlow:
    """Test class for auth redirect flow debugging."""

    @pytest.mark.asyncio
    async def test_login_htmx_flow(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test the complete HTMX login flow with cookie authentication."""
        # Create a test user
        user = User(username="testuser")
        user.set_password("testpassword")
        test_db.add(user)
        test_db.commit()

        # Make login request (HTMX-style)
        response = await async_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "testpassword"},
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            },
        )

        # Should get a 200 OK with HTML success template
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Login successful" in response.text

        # Should have set auth cookie
        assert "auth_token" in response.cookies
        auth_token = response.cookies["auth_token"]
        assert auth_token is not None and len(auth_token) > 0

        # Now try to access the main page with the cookie
        async_client.cookies.set("auth_token", auth_token)
        response2 = await async_client.get(
            "/",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            },
            follow_redirects=False,
        )

        assert response2.status_code == 302
        assert response2.headers["location"] == "/repositories"

        response3 = await async_client.get(
            "/repositories",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            },
            follow_redirects=False,
        )

        assert response3.status_code == 200
        assert "Borgitory" in response3.text

    @pytest.mark.asyncio
    async def test_login_sets_cookie_correctly(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that login sets the cookie with correct attributes via HTMX."""
        # Create a test user
        user = User(username="cookietest")
        user.set_password("testpassword")
        test_db.add(user)
        test_db.commit()

        # Make login request
        response = await async_client.post(
            "/auth/login",
            data={"username": "cookietest", "password": "testpassword"},
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            },
        )

        # Should get success response
        assert response.status_code == 200
        assert "Login successful" in response.text

        set_cookie_header = response.headers.get("set-cookie", "")

        assert "auth_token=" in set_cookie_header
        assert "HttpOnly" in set_cookie_header
        assert "samesite=lax" in set_cookie_header.lower()
