"""
Template Response Utilities for HTMX/JSON handling.
Provides consistent response formatting for API endpoints.
"""

from typing import Optional
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from borgitory.models.repository_dtos import (
    RepositoryOperationResult,
    ArchiveListingResult,
    RepositoryScanResult,
    DeleteRepositoryResult,
)

# Templates will be loaded lazily to avoid circular imports
_templates_cache: Optional[Jinja2Templates] = None


def get_templates_instance() -> Jinja2Templates:
    """Get templates instance with lazy loading to avoid circular imports."""
    global _templates_cache
    if _templates_cache is None:
        from borgitory.dependencies import get_templates

        _templates_cache = get_templates()
    return _templates_cache


class ResponseType:
    """Response type detection."""

    @staticmethod
    def is_htmx_request(request: Request) -> bool:
        """Check if request is from HTMX."""
        return "hx-request" in request.headers

    @staticmethod
    def expects_json(request: Request) -> bool:
        """Check if request expects JSON response."""
        accept_header = request.headers.get("Accept", "")
        return "application/json" in accept_header and not ResponseType.is_htmx_request(
            request
        )


class RepositoryResponseHandler:
    """Handles repository operation responses."""

    @staticmethod
    def handle_create_response(
        request: Request, result: RepositoryOperationResult
    ) -> HTMLResponse:
        """Handle repository creation response."""
        if result.success:
            response = get_templates_instance().TemplateResponse(
                request,
                "partials/repositories/create/form_create_success.html",
                {"repository_name": result.repository_name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            error_message = result.error_message
            if result.is_validation_error and result.validation_errors:
                error_message = result.validation_errors[0].message

            return get_templates_instance().TemplateResponse(
                request,
                "partials/repositories/create/form_create_error.html",
                {"error_message": error_message},
                status_code=200,
            )

    @staticmethod
    def handle_import_response(
        request: Request, result: RepositoryOperationResult
    ) -> HTMLResponse:
        """Handle repository import response."""
        if result.success:
            response = get_templates_instance().TemplateResponse(
                request,
                "partials/repositories/import/form_import_success.html",
                {"repository_name": result.repository_name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            error_message = result.error_message
            if result.is_validation_error and result.validation_errors:
                error_message = result.validation_errors[0].message

            return get_templates_instance().TemplateResponse(
                request,
                "partials/repositories/import/form_import_error.html",
                {"error_message": error_message},
                status_code=200,
            )

    @staticmethod
    def handle_scan_response(
        request: Request, result: RepositoryScanResult
    ) -> HTMLResponse:
        """Handle repository scan response."""
        if result.success:
            return get_templates_instance().TemplateResponse(
                request,
                "partials/repositories/import/scan_results.html",
                {"repositories": [repo.__dict__ for repo in result.repositories]},
            )
        else:
            return get_templates_instance().TemplateResponse(
                request,
                "partials/common/error_message.html",
                {"error_message": f"Error: {result.error_message}"},
            )

    @staticmethod
    def handle_delete_response(
        request: Request, result: DeleteRepositoryResult
    ) -> HTMLResponse:
        """Handle repository deletion response."""
        if result.success:
            return get_templates_instance().TemplateResponse(
                request,
                "partials/repositories/delete_success.html",
                {"repository_name": result.repository_name},
                status_code=200,
            )
        else:
            return get_templates_instance().TemplateResponse(
                request,
                "partials/common/error_message.html",
                {"error_message": result.error_message},
                status_code=200,
            )


class ArchiveResponseHandler:
    """Handles archive operation responses."""

    @staticmethod
    def handle_archive_listing_response(
        request: Request, result: ArchiveListingResult
    ) -> HTMLResponse:
        """Handle archive listing response."""
        if result.success:
            archives_data = [archive.__dict__ for archive in result.archives]
            recent_archives_data = [
                archive.__dict__ for archive in result.recent_archives
            ]

            return get_templates_instance().TemplateResponse(
                request,
                "partials/archives/list_content.html",
                {
                    "repository": {
                        "id": result.repository_id,
                        "name": result.repository_name,
                    },
                    "archives": archives_data,
                    "recent_archives": recent_archives_data,
                },
            )
        else:
            return get_templates_instance().TemplateResponse(
                request,
                "partials/archives/error_message.html",
                {
                    "error_message": result.error_message,
                    "show_help": True,
                },
            )
