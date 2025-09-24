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
