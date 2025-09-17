"""
Basic test to verify testing setup works
"""

import pytest
from httpx import AsyncClient


class TestBasic:
    """Basic test class."""

    @pytest.mark.asyncio
    async def test_basic_functionality(self, async_client: AsyncClient) -> None:
        """Test that the test client can make requests."""
        # Test a simple endpoint - this might fail due to auth but should at least connect
        response = await async_client.get("/")

        # We expect some response, not necessarily 200 due to auth (302 is redirect)
        assert response.status_code in [200, 302, 404, 422, 401]

    def test_simple_assertion(self) -> None:
        """Test that basic pytest functionality works."""
        assert 1 + 1 == 2
