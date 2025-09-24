"""
Tests for package selection endpoints and HTMX functionality.
Tests the frontend behavior and template rendering for package selection.
"""

import pytest
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.models.database import User
from borgitory.services.package_manager_service import PackageManagerService
from borgitory.dependencies import get_templates, get_package_manager_service
from borgitory.api.auth import get_current_user

client = TestClient(app)


class TestPackageSelectionEndpoints:
    """Test package selection HTMX endpoints"""

    @pytest.fixture(scope="function")
    def setup_test_dependencies(self, test_db: Session) -> Dict[str, Any]:
        """Setup dependency overrides for each test."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)
        mock_package_service.install_packages = AsyncMock(
            return_value=(True, "Installation successful")
        )

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates service that returns proper HTMLResponse
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            """Mock template response that returns HTMLResponse"""
            # For testing, we can include context data in the HTML content
            context_str = ""
            if context and "selected_packages" in context:
                packages = context["selected_packages"]
                context_str = f" data-packages='{','.join(packages)}'"
            elif context and "error" in context:
                context_str = f" data-error='{context['error']}'"
            elif context and "packages" in context:
                packages = context["packages"]
                context_str = f" data-installed-packages='{','.join(packages)}'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response for {template_name}</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_select_package_empty_form(self, setup_test_dependencies: Dict[str, Any]):
        """Test selecting a package with no existing selections"""
        try:
            response = client.post(
                "/api/packages/select", data={"package_name": "curl"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Check that the correct template was rendered and contains curl
            content = response.text
            assert "data-template='partials/packages/selected_packages.html'" in content
            assert "data-packages='curl'" in content

        finally:
            app.dependency_overrides.clear()

    def test_select_package_with_existing_selections(
        self, setup_test_dependencies: Dict[str, Any]
    ):
        """Test selecting a package when others are already selected"""
        try:
            response = client.post(
                "/api/packages/select",
                data={
                    "package_name": "jq",
                    "selected_package_0": "curl",
                    "selected_package_1": "sqlite3",
                },
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Check that all three packages are in the response
            content = response.text
            assert "data-template='partials/packages/selected_packages.html'" in content
            # The packages should be in the data-packages attribute
            assert "curl" in content
            assert "sqlite3" in content
            assert "jq" in content

        finally:
            app.dependency_overrides.clear()

    def test_clear_selections(self, setup_test_dependencies: Dict[str, Any]):
        """Test clearing all package selections"""
        try:
            response = client.get("/api/packages/clear-selections")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should render the selected_packages template with empty packages
            content = response.text
            assert "data-template='partials/packages/selected_packages.html'" in content
            assert "data-packages=''" in content

        finally:
            app.dependency_overrides.clear()

    def test_install_with_selected_packages(
        self, setup_test_dependencies: Dict[str, Any]
    ):
        """Test installing packages using the new form field format"""
        mock_package_service = setup_test_dependencies["package_service"]

        try:
            response = client.post(
                "/api/packages/install",
                data={
                    "selected_package_0": "curl",
                    "selected_package_1": "jq",
                    "selected_package_2": "sqlite3",
                },
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should have called install_packages with the correct packages
            mock_package_service.install_packages.assert_called_once_with(
                ["curl", "jq", "sqlite3"]
            )

            # Should render success template
            content = response.text
            assert "data-template='partials/packages/install_success.html'" in content
            assert "data-installed-packages='curl,jq,sqlite3'" in content

        finally:
            app.dependency_overrides.clear()

    def test_install_with_no_selections(self, setup_test_dependencies: Dict[str, Any]):
        """Test installing with no packages selected"""
        mock_package_service = setup_test_dependencies["package_service"]

        try:
            response = client.post("/api/packages/install", data={})

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should not call install_packages
            mock_package_service.install_packages.assert_not_called()

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/install_error.html'" in content
            assert "No packages selected" in content

        finally:
            app.dependency_overrides.clear()

    def test_install_success_triggers_clear_selections(
        self, setup_test_dependencies: Dict[str, Any]
    ):
        """Test that successful install triggers clear-selections"""
        mock_package_service = setup_test_dependencies["package_service"]
        mock_package_service.install_packages.return_value = (
            True,
            "Installed successfully",
        )

        try:
            response = client.post(
                "/api/packages/install", data={"selected_package_0": "curl"}
            )

            assert response.status_code == 200

            # Check that HX-Trigger header is set
            assert "HX-Trigger" in response.headers
            assert response.headers["HX-Trigger"] == "clear-selections"

        finally:
            app.dependency_overrides.clear()

    def test_install_failure_no_trigger(self, setup_test_dependencies: Dict[str, Any]):
        """Test that failed install doesn't trigger clear-selections"""
        mock_package_service = setup_test_dependencies["package_service"]
        mock_package_service.install_packages.return_value = (
            False,
            "Installation failed",
        )

        try:
            response = client.post(
                "/api/packages/install", data={"selected_package_0": "nonexistent"}
            )

            assert response.status_code == 200

            # Should not have HX-Trigger header
            assert "HX-Trigger" not in response.headers

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/install_error.html'" in content
            assert "Installation failed" in content

        finally:
            app.dependency_overrides.clear()

    def test_missing_package_name_validation(
        self, setup_test_dependencies: Dict[str, Any]
    ):
        """Test select endpoint without package_name"""
        try:
            response = client.post("/api/packages/select", data={})

            # Should return validation error
            assert response.status_code == 422

        finally:
            app.dependency_overrides.clear()


class TestPackageRemovalEndpoints:
    """Test package removal functionality"""

    @pytest.fixture(scope="function")
    def setup_removal_test(self, test_db: Session) -> Dict[str, Any]:
        """Setup for removal tests."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            context_str = ""
            if context and "selected_packages" in context:
                packages = context["selected_packages"]
                context_str = f" data-packages='{','.join(packages)}'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_remove_package_selection(self, setup_removal_test: Dict[str, Any]):
        """Test removing a package from selections"""
        try:
            response = client.post(
                "/api/packages/remove-selection",
                data={
                    "package_name": "curl",
                    "selected_package_0": "curl",
                    "selected_package_1": "jq",
                    "selected_package_2": "sqlite3",
                },
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should render selected_packages template
            content = response.text
            assert "data-template='partials/packages/selected_packages.html'" in content
            # Should have the remaining packages (curl should be removed)
            assert "jq,sqlite3" in content

        finally:
            app.dependency_overrides.clear()

    def test_remove_nonexistent_package(self, setup_removal_test: Dict[str, Any]):
        """Test removing a package that's not in selections"""
        try:
            response = client.post(
                "/api/packages/remove-selection",
                data={
                    "package_name": "nonexistent",
                    "selected_package_0": "curl",
                    "selected_package_1": "jq",
                },
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should render selected_packages template with original packages
            content = response.text
            assert "data-template='partials/packages/selected_packages.html'" in content
            assert "curl,jq" in content

        finally:
            app.dependency_overrides.clear()


class TestErrorHandling:
    """Test error handling in package selection endpoints"""

    @pytest.fixture(scope="function")
    def setup_error_test(self, test_db: Session) -> Dict[str, Any]:
        """Setup for error handling tests."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            context_str = ""
            if context and "error" in context:
                context_str = " data-error='error'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_package_service_error_handling(self, setup_error_test: Dict[str, Any]):
        """Test handling of package service errors"""
        mock_package_service = setup_error_test["package_service"]
        mock_package_service.install_packages = AsyncMock(
            side_effect=Exception("Service error")
        )

        try:
            response = client.post(
                "/api/packages/install", data={"selected_package_0": "curl"}
            )

            # Should handle error gracefully and return error template
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            content = response.text
            assert "data-template='partials/packages/install_error.html'" in content

        finally:
            app.dependency_overrides.clear()


class TestPackageSearchEndpoints:
    """Test package search and autocomplete functionality"""

    @pytest.fixture(scope="function")
    def setup_search_test(self, test_db: Session) -> Dict[str, Any]:
        """Setup for search tests."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)

        # Mock search results
        from borgitory.services.package_manager_service import PackageInfo

        mock_packages = [
            PackageInfo(
                name="curl",
                version="7.81.0-1",
                description="command line tool for transferring data with URL syntax",
                section="web",
                installed=False,
            ),
            PackageInfo(
                name="curl-dev",
                version="7.81.0-1",
                description="development files for curl",
                section="libdevel",
                installed=True,
            ),
        ]
        mock_package_service.search_packages = AsyncMock(return_value=mock_packages)

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            context_str = ""
            if context and "packages" in context:
                packages = context["packages"]
                context_str = f" data-package-count='{len(packages)}'"
                if packages:
                    first_package = packages[0].name
                    context_str += f" data-first-package='{first_package}'"
            elif context and "message" in context:
                context_str = f" data-message='{context['message']}'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_search_packages_autocomplete_valid_query(
        self, setup_search_test: Dict[str, Any]
    ):
        """Test package search with valid query"""
        mock_package_service = setup_search_test["package_service"]

        try:
            response = client.get("/api/packages/search/autocomplete?search=curl")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should have called search_packages
            mock_package_service.search_packages.assert_called_once_with(
                "curl", limit=20
            )

            # Should render search results template
            content = response.text
            assert "data-template='partials/packages/search_results.html'" in content
            assert "data-package-count='2'" in content
            assert "data-first-package='curl'" in content

        finally:
            app.dependency_overrides.clear()

    def test_search_packages_autocomplete_short_query(
        self, setup_search_test: Dict[str, Any]
    ):
        """Test package search with query too short"""
        mock_package_service = setup_search_test["package_service"]

        try:
            response = client.get("/api/packages/search/autocomplete?search=c")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should not call search_packages
            mock_package_service.search_packages.assert_not_called()

            # Should render empty search template
            content = response.text
            assert "data-template='partials/packages/empty_search.html'" in content
            assert "Type at least 2 characters" in content

        finally:
            app.dependency_overrides.clear()

    def test_search_packages_autocomplete_empty_query(
        self, setup_search_test: Dict[str, Any]
    ):
        """Test package search with empty query"""
        mock_package_service = setup_search_test["package_service"]

        try:
            response = client.get("/api/packages/search/autocomplete")

            assert response.status_code == 200

            # Should not call search_packages
            mock_package_service.search_packages.assert_not_called()

            # Should render empty search template
            content = response.text
            assert "data-template='partials/packages/empty_search.html'" in content

        finally:
            app.dependency_overrides.clear()

    def test_search_packages_autocomplete_service_error(
        self, setup_search_test: Dict[str, Any]
    ):
        """Test package search with service error"""
        mock_package_service = setup_search_test["package_service"]
        mock_package_service.search_packages = AsyncMock(
            side_effect=Exception("Search failed")
        )

        try:
            response = client.get("/api/packages/search/autocomplete?search=curl")

            assert response.status_code == 200

            # Should render search error template
            content = response.text
            assert "data-template='partials/packages/search_error.html'" in content

        finally:
            app.dependency_overrides.clear()


class TestInstalledPackagesEndpoint:
    """Test listing installed packages"""

    @pytest.fixture(scope="function")
    def setup_installed_test(self, test_db: Session) -> Dict[str, Any]:
        """Setup for installed packages tests."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)

        # Mock installed packages
        from borgitory.services.package_manager_service import PackageInfo
        from borgitory.models.database import UserInstalledPackage

        mock_packages = [
            PackageInfo(
                name="curl",
                version="7.81.0-1",
                description="command line tool",
                section="web",
                installed=True,
            ),
            PackageInfo(
                name="jq",
                version="1.6-2.1",
                description="lightweight JSON processor",
                section="utils",
                installed=True,
            ),
        ]

        # Mock user-installed packages
        mock_user_package = Mock(spec=UserInstalledPackage)
        mock_user_package.package_name = "curl"

        mock_package_service.list_installed_packages = AsyncMock(
            return_value=mock_packages
        )
        mock_package_service.get_user_installed_packages = Mock(
            return_value=[mock_user_package]
        )

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            context_str = ""
            if context and "packages" in context:
                packages = context["packages"]
                context_str = f" data-package-count='{len(packages)}'"
                # Check if any packages are marked as user_installed
                user_installed_count = sum(
                    1 for p in packages if getattr(p, "user_installed", False)
                )
                context_str += f" data-user-installed-count='{user_installed_count}'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_list_installed_packages_success(
        self, setup_installed_test: Dict[str, Any]
    ):
        """Test listing installed packages successfully"""
        mock_package_service = setup_installed_test["package_service"]

        try:
            response = client.get("/api/packages/installed")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should have called the service methods
            mock_package_service.list_installed_packages.assert_called_once()
            mock_package_service.get_user_installed_packages.assert_called_once()

            # Should render installed list template
            content = response.text
            assert "data-template='partials/packages/installed_list.html'" in content
            assert "data-package-count='2'" in content
            assert (
                "data-user-installed-count='1'" in content
            )  # curl should be marked as user-installed

        finally:
            app.dependency_overrides.clear()

    def test_list_installed_packages_service_error(
        self, setup_installed_test: Dict[str, Any]
    ):
        """Test listing installed packages with service error"""
        mock_package_service = setup_installed_test["package_service"]
        mock_package_service.list_installed_packages = AsyncMock(
            side_effect=Exception("Failed to list packages")
        )

        try:
            response = client.get("/api/packages/installed")

            assert response.status_code == 200

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/error.html'" in content

        finally:
            app.dependency_overrides.clear()


class TestPackageRemovalEndpoint:
    """Test package removal functionality"""

    @pytest.fixture(scope="function")
    def setup_removal_endpoint_test(self, test_db: Session) -> Dict[str, Any]:
        """Setup for package removal tests."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)
        mock_package_service.remove_packages = AsyncMock(
            return_value=(True, "Removal successful")
        )

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            context_str = ""
            if context and "packages" in context:
                packages = context["packages"]
                context_str = f" data-removed-packages='{','.join(packages)}'"
            elif context and "error" in context:
                error_msg = context["error"]
                context_str = f" data-error='{error_msg}'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_remove_packages_success(self, setup_removal_endpoint_test: Dict[str, Any]):
        """Test removing packages successfully"""
        mock_package_service = setup_removal_endpoint_test["package_service"]

        try:
            response = client.post(
                "/api/packages/remove",
                data={
                    "remove_package_0": "curl",
                    "remove_package_1": "jq",
                },
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should have called remove_packages with correct packages
            mock_package_service.remove_packages.assert_called_once_with(["curl", "jq"])

            # Should render success template
            content = response.text
            assert "data-template='partials/packages/remove_success.html'" in content
            assert "data-removed-packages='curl,jq'" in content

        finally:
            app.dependency_overrides.clear()

    def test_remove_packages_no_selection(
        self, setup_removal_endpoint_test: Dict[str, Any]
    ):
        """Test removing packages with no selection"""
        mock_package_service = setup_removal_endpoint_test["package_service"]

        try:
            response = client.post("/api/packages/remove", data={})

            assert response.status_code == 200

            # Should not call remove_packages
            mock_package_service.remove_packages.assert_not_called()

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/remove_error.html'" in content
            assert "No packages selected for removal" in content

        finally:
            app.dependency_overrides.clear()

    def test_remove_packages_service_failure(
        self, setup_removal_endpoint_test: Dict[str, Any]
    ):
        """Test removing packages with service failure"""
        mock_package_service = setup_removal_endpoint_test["package_service"]
        mock_package_service.remove_packages.return_value = (False, "Removal failed")

        try:
            response = client.post(
                "/api/packages/remove",
                data={"remove_package_0": "nonexistent"},
            )

            assert response.status_code == 200

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/remove_error.html'" in content

        finally:
            app.dependency_overrides.clear()

    def test_remove_packages_service_exception(
        self, setup_removal_endpoint_test: Dict[str, Any]
    ):
        """Test removing packages with service exception"""
        mock_package_service = setup_removal_endpoint_test["package_service"]
        mock_package_service.remove_packages = AsyncMock(
            side_effect=Exception("Service error")
        )

        try:
            response = client.post(
                "/api/packages/remove",
                data={"remove_package_0": "curl"},
            )

            assert response.status_code == 200

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/remove_error.html'" in content

        finally:
            app.dependency_overrides.clear()


class TestPackageInfoEndpoint:
    """Test package info functionality"""

    @pytest.fixture(scope="function")
    def setup_info_test(self, test_db: Session) -> Dict[str, Any]:
        """Setup for package info tests."""
        # Create mock current user
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        # Create mock package service
        mock_package_service = Mock(spec=PackageManagerService)

        # Mock package info
        from borgitory.services.package_manager_service import PackageInfo

        mock_package_info = PackageInfo(
            name="curl",
            version="7.81.0-1",
            description="command line tool for transferring data with URL syntax",
            section="web",
            installed=True,
        )
        mock_package_service.get_package_info = AsyncMock(
            return_value=mock_package_info
        )

        def override_get_package_service() -> PackageManagerService:
            return mock_package_service

        # Create mock templates
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            context_str = ""
            if context and "package" in context:
                package = context["package"]
                context_str = f" data-package-name='{package.name}' data-package-version='{package.version}'"

            return HTMLResponse(
                content=f"<div data-template='{template_name}'{context_str}>Mock response</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        def override_get_templates():
            return mock_templates

        # Apply overrides
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_package_manager_service] = (
            override_get_package_service
        )
        app.dependency_overrides[get_templates] = override_get_templates

        return {
            "user": test_user,
            "package_service": mock_package_service,
            "templates": mock_templates,
        }

    def test_get_package_info_success(self, setup_info_test: Dict[str, Any]):
        """Test getting package info successfully"""
        mock_package_service = setup_info_test["package_service"]

        try:
            response = client.get("/api/packages/curl/info")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Should have called get_package_info
            mock_package_service.get_package_info.assert_called_once_with("curl")

            # Should render package info template
            content = response.text
            assert "data-template='partials/packages/package_info.html'" in content
            assert "data-package-name='curl'" in content
            assert "data-package-version='7.81.0-1'" in content

        finally:
            app.dependency_overrides.clear()

    def test_get_package_info_not_found(self, setup_info_test: Dict[str, Any]):
        """Test getting package info for non-existent package"""
        mock_package_service = setup_info_test["package_service"]
        mock_package_service.get_package_info = AsyncMock(return_value=None)

        try:
            response = client.get("/api/packages/nonexistent/info")

            # Should return 500 due to HTTPException being caught by general exception handler
            assert response.status_code == 500

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/error.html'" in content

        finally:
            app.dependency_overrides.clear()

    def test_get_package_info_value_error(self, setup_info_test: Dict[str, Any]):
        """Test getting package info with invalid package name"""
        mock_package_service = setup_info_test["package_service"]
        mock_package_service.get_package_info = AsyncMock(
            side_effect=ValueError("Invalid package name")
        )

        try:
            response = client.get("/api/packages/invalid!/info")

            assert response.status_code == 400

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/error.html'" in content

        finally:
            app.dependency_overrides.clear()

    def test_get_package_info_service_error(self, setup_info_test: Dict[str, Any]):
        """Test getting package info with service error"""
        mock_package_service = setup_info_test["package_service"]
        mock_package_service.get_package_info = AsyncMock(
            side_effect=Exception("Service error")
        )

        try:
            response = client.get("/api/packages/curl/info")

            assert response.status_code == 500

            # Should render error template
            content = response.text
            assert "data-template='partials/packages/error.html'" in content

        finally:
            app.dependency_overrides.clear()
