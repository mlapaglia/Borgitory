"""
Tests for repository archives navigation functionality

This module tests the "View Archives" button functionality in the repository list
and ensures it properly navigates to the archives tab with preselected repository.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from typing import Any, Generator

from borgitory.main import app
from borgitory.api.auth import get_current_user
from borgitory.models.database import User, Repository


@pytest.fixture
def mock_current_user(test_db: Session) -> Generator[User, None, None]:
    """Create a mock current user for testing."""
    test_user = User()
    test_user.username = "testuser"
    test_user.set_password("testpass")
    test_db.add(test_user)
    test_db.commit()
    test_db.refresh(test_user)

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield test_user
    app.dependency_overrides.clear()


class TestRepositoryArchivesNavigation:
    """Test class for repository archives navigation functionality."""

    @pytest.mark.asyncio
    async def test_repository_list_contains_view_archives_button(
        self, async_client: AsyncClient, test_db: Session, mock_current_user: Any
    ) -> None:
        """Test that repository list contains properly configured View Archives buttons."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "test-repo-1"
        repo1.path = "/tmp/test-repo-1"
        repo1.set_passphrase("pass1")
        repo2 = Repository()
        repo2.name = "test-repo-2"
        repo2.path = "/tmp/test-repo-2"
        repo2.set_passphrase("pass2")

        test_db.add_all([repo1, repo2])
        test_db.commit()

        # Get repository list HTML
        response = await async_client.get("/api/repositories/html")
        assert response.status_code == 200
        content = response.text

        # Check that View Archives buttons exist for each repository
        assert content.count("View Archives") == 2

        # Check that buttons have correct HTMX attributes for sidenav navigation
        assert 'hx-get="/api/tabs/archives"' in content
        assert 'hx-target="#main-content"' in content
        assert 'hx-swap="innerHTML"' in content
        assert 'hx-push-url="/archives"' in content

        # Check that preselect_repo parameters are set correctly
        assert f'"preselect_repo": "{repo1.id}"' in content
        assert f'"preselect_repo": "{repo2.id}"' in content

    @pytest.mark.asyncio
    async def test_view_archives_button_navigation_flow(
        self, async_client: AsyncClient, test_db: Session, mock_current_user: Any
    ) -> None:
        """Test the complete navigation flow when clicking View Archives."""
        # Create test repository
        repo = Repository()
        repo.name = "navigation-test-repo"
        repo.path = "/tmp/navigation-test"
        repo.set_passphrase("navpass")
        test_db.add(repo)
        test_db.commit()

        # Simulate clicking the View Archives button by calling the archives tab with preselect_repo
        response = await async_client.get(
            f"/api/tabs/archives?preselect_repo={repo.id}"
        )
        assert response.status_code == 200
        content = response.text

        # Check that archives tab loads
        assert "Archive Browser" in content
        assert "Select Repository" in content

        # Check that the preselect_repo parameter is passed to the selector
        assert f"preselect_repo={repo.id}" in content

    @pytest.mark.asyncio
    async def test_archives_tab_selector_with_preselected_repository(
        self, async_client: AsyncClient, test_db: Session, mock_current_user: Any
    ) -> None:
        """Test that the archives selector correctly handles preselected repository."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "selector-repo-1"
        repo1.path = "/tmp/selector-1"
        repo1.set_passphrase("sel1")
        repo2 = Repository()
        repo2.name = "selector-repo-2"
        repo2.path = "/tmp/selector-2"
        repo2.set_passphrase("sel2")

        test_db.add_all([repo1, repo2])
        test_db.commit()

        # Test archives selector with preselected repository
        response = await async_client.get(
            f"/api/repositories/archives/selector?preselect_repo={repo1.id}",
            headers={"hx-request": "true"},
        )
        assert response.status_code == 200
        content = response.text

        # Check that repo1 is selected
        assert f'value="{repo1.id}" selected' in content
        assert f'value="{repo2.id}" selected' not in content

        # Check that both repositories are available as options
        assert "selector-repo-1" in content
        assert "selector-repo-2" in content

        # Check that HTMX triggers include load for auto-triggering
        assert 'hx-trigger="change, load"' in content

    @pytest.mark.asyncio
    async def test_archives_selector_without_preselection(
        self, async_client: AsyncClient, test_db: Session, mock_current_user: Any
    ) -> None:
        """Test that archives selector works normally without preselection."""
        # Create test repository
        repo = Repository()
        repo.name = "normal-repo"
        repo.path = "/tmp/normal"
        repo.set_passphrase("normal")
        test_db.add(repo)
        test_db.commit()

        # Test archives selector without preselection
        response = await async_client.get(
            "/api/repositories/archives/selector", headers={"hx-request": "true"}
        )
        assert response.status_code == 200
        content = response.text

        # Check that no repository is selected
        assert "selected" not in content
        assert "Select a repository to view archives..." in content

        # Check that repository is available as option
        assert "normal-repo" in content

        # Check that HTMX trigger is only 'change' (no load trigger)
        assert 'hx-trigger="change"' in content
        assert 'hx-trigger="change, load"' not in content

    @pytest.mark.asyncio
    async def test_view_archives_button_with_nonexistent_repository(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test View Archives navigation with non-existent repository ID."""
        # Test archives tab with non-existent repository ID
        response = await async_client.get("/api/tabs/archives?preselect_repo=999")
        assert response.status_code == 200
        content = response.text

        # Should still load archives tab successfully
        assert "Archive Browser" in content

        # Test archives selector with non-existent repository ID
        response = await async_client.get(
            "/api/repositories/archives/selector?preselect_repo=999",
            headers={"hx-request": "true"},
        )
        assert response.status_code == 200
        content = response.text

        # Should not have any selected repository
        assert "selected" not in content
        assert "Select a repository to view archives..." in content

    @pytest.mark.asyncio
    async def test_empty_repository_list_archives_buttons(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test repository list when no repositories exist."""
        # Get repository list HTML with no repositories
        response = await async_client.get("/api/repositories/html")
        assert response.status_code == 200
        content = response.text

        # Should show empty state
        assert "No repositories configured" in content
        assert "View Archives" not in content

    @pytest.mark.asyncio
    async def test_archives_tab_oob_navigation_update(
        self, async_client: AsyncClient, test_db: Session, mock_current_user: Any
    ) -> None:
        """Test that archives tab includes out-of-band navigation update."""
        # Create test repository
        repo = Repository()
        repo.name = "oob-test-repo"
        repo.path = "/tmp/oob-test"
        repo.set_passphrase("oobpass")
        test_db.add(repo)
        test_db.commit()

        # Test archives tab response
        response = await async_client.get(
            f"/api/tabs/archives?preselect_repo={repo.id}"
        )
        assert response.status_code == 200
        content = response.text

        # Check for out-of-band update for sidebar navigation
        assert 'hx-swap-oob="outerHTML:#sidebar"' in content

        # Check that archives is marked as active in navigation
        assert "active" in content  # Should have active class somewhere for archives
