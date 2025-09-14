"""
Template Response Utilities for HTMX/JSON handling.
Provides consistent response formatting for API endpoints.
"""

from typing import Any, Dict, Optional, Union
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from models.repository_dtos import (
    RepositoryOperationResult,
    ArchiveListingResult,
    RepositoryScanResult,
    DirectoryListingResult,
    ArchiveContentsResult,
    RepositoryInfoResult,
    DeleteRepositoryResult,
)

# Initialize templates
templates = Jinja2Templates(directory="src/templates")


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
        return "application/json" in accept_header and not ResponseType.is_htmx_request(request)


class RepositoryResponseHandler:
    """Handles repository operation responses."""

    @staticmethod
    def handle_create_response(
        request: Request, result: RepositoryOperationResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle repository creation response."""
        if result.success:
            if ResponseType.is_htmx_request(request):
                response = templates.TemplateResponse(
                    request,
                    "partials/repositories/form_create_success.html",
                    {"repository_name": result.repository_name},
                )
                response.headers["HX-Trigger"] = "repositoryUpdate"
                return response
            else:
                return {
                    "success": True,
                    "repository_id": result.repository_id,
                    "repository_name": result.repository_name,
                    "message": result.message,
                }
        else:
            error_message = result.error_message
            if result.is_validation_error and result.validation_errors:
                error_message = result.validation_errors[0].message

            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_create_error.html",
                    {"error_message": error_message},
                    status_code=200,
                )
            else:
                status_code = 400 if result.is_validation_error or result.is_borg_error else 500
                raise HTTPException(status_code=status_code, detail=error_message)

    @staticmethod
    def handle_import_response(
        request: Request, result: RepositoryOperationResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle repository import response."""
        if result.success:
            if ResponseType.is_htmx_request(request):
                response = templates.TemplateResponse(
                    request,
                    "partials/repositories/form_import_success.html",
                    {"repository_name": result.repository_name},
                )
                response.headers["HX-Trigger"] = "repositoryUpdate"
                return response
            else:
                return {
                    "success": True,
                    "repository_id": result.repository_id,
                    "repository_name": result.repository_name,
                    "message": result.message,
                }
        else:
            error_message = result.error_message
            if result.is_validation_error and result.validation_errors:
                error_message = result.validation_errors[0].message

            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_import_error.html",
                    {"error_message": error_message},
                    status_code=200,
                )
            else:
                status_code = 400 if result.is_validation_error or result.is_borg_error else 500
                raise HTTPException(status_code=status_code, detail=error_message)

    @staticmethod
    def handle_scan_response(
        request: Request, result: RepositoryScanResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle repository scan response."""
        if result.success:
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/scan_results.html",
                    {"repositories": [repo.__dict__ for repo in result.repositories]},
                )
            else:
                return {
                    "repositories": [repo.__dict__ for repo in result.repositories]
                }
        else:
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/common/error_message.html",
                    {"error_message": f"Error: {result.error_message}"},
                )
            else:
                raise HTTPException(
                    status_code=500, detail=f"Failed to scan repositories: {result.error_message}"
                )

    @staticmethod
    def handle_delete_response(
        request: Request, result: DeleteRepositoryResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle repository deletion response."""
        if result.success:
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/delete_success.html",
                    {"repository_name": result.repository_name},
                    status_code=200,
                )
            else:
                return {"success": True, "message": result.message or "Repository deleted successfully"}
        else:
            status_code = 409 if result.has_conflicts else 500
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/common/error_message.html",
                    {"error_message": result.error_message},
                    status_code=200,
                )
            else:
                raise HTTPException(status_code=status_code, detail=result.error_message)


class ArchiveResponseHandler:
    """Handles archive operation responses."""

    @staticmethod
    def handle_archive_listing_response(
        request: Request, result: ArchiveListingResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle archive listing response."""
        if result.success:
            if ResponseType.is_htmx_request(request):
                # Convert DTOs to dicts for template
                archives_data = [archive.__dict__ for archive in result.archives]
                recent_archives_data = [archive.__dict__ for archive in result.recent_archives]

                return templates.TemplateResponse(
                    request,
                    "partials/archives/list_content.html",
                    {
                        "repository": {"id": result.repository_id, "name": result.repository_name},
                        "archives": archives_data,
                        "recent_archives": recent_archives_data,
                    },
                )
            else:
                return {
                    "repository_id": result.repository_id,
                    "repository_name": result.repository_name,
                    "archive_count": result.archive_count,
                    "archives": [archive.__dict__ for archive in result.archives],
                }
        else:
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/archives/error_message.html",
                    {
                        "error_message": result.error_message,
                        "show_help": True,
                    },
                )
            else:
                raise HTTPException(status_code=500, detail=result.error_message)

    @staticmethod
    def handle_archive_contents_response(
        request: Request, result: ArchiveContentsResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle archive contents response."""
        if result.success:
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/archives/directory_contents.html",
                    {
                        "repository": {"id": result.repository_id},
                        "archive_name": result.archive_name,
                        "path": result.path,
                        "items": [item.__dict__ for item in result.items],
                        "breadcrumb_parts": result.breadcrumb_parts,
                    },
                )
            else:
                return {
                    "repository_id": result.repository_id,
                    "archive_name": result.archive_name,
                    "path": result.path,
                    "items": [item.__dict__ for item in result.items],
                    "breadcrumb_parts": result.breadcrumb_parts,
                }
        else:
            if ResponseType.is_htmx_request(request):
                return templates.TemplateResponse(
                    request,
                    "partials/common/error_message.html",
                    {"error_message": result.error_message},
                )
            else:
                raise HTTPException(status_code=500, detail=result.error_message)


class DirectoryResponseHandler:
    """Handles directory operation responses."""

    @staticmethod
    def handle_directory_listing_response(
        request: Request, result: DirectoryListingResult
    ) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
        """Handle directory listing response."""
        if result.success:
            return {"directories": result.directories}
        else:
            raise HTTPException(status_code=500, detail=result.error_message)


class GeneralResponseHandler:
    """Handles general responses."""

    @staticmethod
    def handle_repository_info_response(
        request: Request, result: RepositoryInfoResult
    ) -> Union[Dict[str, Any], HTTPException]:
        """Handle repository info response."""
        if result.success:
            return result.info
        else:
            raise HTTPException(status_code=500, detail=result.error_message)

    @staticmethod
    def handle_repositories_html_response(
        request: Request, repositories: list
    ) -> HTMLResponse:
        """Handle repositories HTML listing response."""
        try:
            return templates.TemplateResponse(
                request,
                "partials/repositories/list_content.html",
                {"repositories": repositories},
            )
        except Exception as e:
            return templates.TemplateResponse(
                request,
                "partials/common/error_message.html",
                {"error_message": f"Error loading repositories: {str(e)}"},
            )

    @staticmethod
    def handle_form_response(request: Request, template_name: str) -> HTMLResponse:
        """Handle form template responses."""
        return templates.TemplateResponse(request, template_name)


# Convenience functions for common operations
def handle_repository_operation_response(
    request: Request, result: RepositoryOperationResult, operation_type: str
) -> Union[HTMLResponse, Dict[str, Any], HTTPException]:
    """Handle repository operation response based on operation type."""
    if operation_type == "create":
        return RepositoryResponseHandler.handle_create_response(request, result)
    elif operation_type == "import":
        return RepositoryResponseHandler.handle_import_response(request, result)
    else:
        raise ValueError(f"Unknown repository operation type: {operation_type}")


def handle_error_response(
    request: Request, error_message: str, status_code: int = 500
) -> Union[HTMLResponse, HTTPException]:
    """Handle generic error response."""
    if ResponseType.is_htmx_request(request):
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": error_message},
            status_code=200,
        )
    else:
        raise HTTPException(status_code=status_code, detail=error_message)


def handle_success_response(
    request: Request, data: Dict[str, Any], template_name: Optional[str] = None
) -> Union[HTMLResponse, Dict[str, Any]]:
    """Handle generic success response."""
    if ResponseType.is_htmx_request(request) and template_name:
        return templates.TemplateResponse(request, template_name, data)
    else:
        return data