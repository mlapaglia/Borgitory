"""
Tests for repositories API endpoints
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.models.database import Repository


class TestRepositoriesAPI:
    """Test class for repositories API endpoints."""

    @pytest.mark.asyncio
    async def test_list_repositories_empty(self, async_client: AsyncClient) -> None:
        """Test listing repositories when empty."""
        response = await async_client.get("/api/repositories/")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_repositories_with_data(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """Test listing repositories with data."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "repo-1"
        repo1.path = "/tmp/repo-1"
        repo1.set_passphrase("passphrase-1")
        repo2 = Repository()
        repo2.name = "repo-2"
        repo2.path = "/tmp/repo-2"
        repo2.set_passphrase("passphrase-2")

        test_db.add_all([repo1, repo2])
        test_db.commit()

        response = await async_client.get("/api/repositories/")

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
        assert response_data[0]["name"] == "repo-1"
        assert response_data[1]["name"] == "repo-2"

    @pytest.mark.asyncio
    async def test_list_repositories_pagination(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """Test listing repositories with pagination."""
        # Create multiple repositories
        for i in range(5):
            repo = Repository()
            repo.name = f"repo-{i}"
            repo.path = f"/tmp/repo-{i}"
            repo.set_passphrase(f"passphrase-{i}")
            test_db.add(repo)
        test_db.commit()

        # Test with limit
        response = await async_client.get("/api/repositories/?skip=1&limit=2")

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
