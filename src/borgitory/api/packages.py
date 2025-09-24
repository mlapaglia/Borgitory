"""
Package Management API endpoints.
Provides functionality to search, install, and manage Debian packages.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.templating import _TemplateResponse

from borgitory.dependencies import PackageManagerServiceDep, TemplatesDep
from borgitory.models.database import User
from borgitory.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/search/autocomplete", response_class=HTMLResponse)
async def search_packages_autocomplete(
    request: Request,
    templates: TemplatesDep,
    package_service: PackageManagerServiceDep,
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Search packages for autocomplete functionality."""

    # Get the search query from form data or query params
    form_data = (
        await request.form() if request.method == "POST" else request.query_params
    )

    query = ""
    # Try to get the input value from various possible parameter names
    for param_name in form_data.keys():
        if param_name in ["package_search", "package_name", "search"]:
            value = form_data[param_name]
            query = value if isinstance(value, str) else ""
            break

    if not query or len(query) < 2:
        # Get the target input ID from headers
        target_input = request.headers.get("hx-target-input", "package-search")
        return templates.TemplateResponse(
            request,
            "partials/packages/empty_search.html",
            {
                "message": "Type at least 2 characters to search packages",
                "input_id": target_input,
            },
        )

    try:
        packages = await package_service.search_packages(query, limit=20)

        # Get the target input ID from headers
        target_input = request.headers.get("hx-target-input", "package-search")

        return templates.TemplateResponse(
            request,
            "partials/packages/search_results.html",
            {"packages": packages, "query": query, "input_id": target_input},
        )

    except Exception as e:
        logger.error(f"Error searching packages: {e}")
        # Get the target input ID from headers
        target_input = request.headers.get("hx-target-input", "package-search")
        return templates.TemplateResponse(
            request,
            "partials/packages/search_error.html",
            {"error": str(e), "input_id": target_input},
        )


@router.get("/installed", response_class=HTMLResponse)
async def list_installed_packages(
    request: Request,
    templates: TemplatesDep,
    package_service: PackageManagerServiceDep,
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """List all installed packages."""

    try:
        # Get all installed packages
        packages = await package_service.list_installed_packages()

        # Get user-installed packages from database
        user_packages = package_service.get_user_installed_packages()
        user_package_names = {pkg.package_name for pkg in user_packages}

        # Add user_installed flag to packages
        for package in packages:
            package.user_installed = package.name in user_package_names

        return templates.TemplateResponse(
            request,
            "partials/packages/installed_list.html",
            {"packages": packages, "user_packages": user_packages},
        )

    except Exception as e:
        logger.error(f"Error listing installed packages: {e}")
        return templates.TemplateResponse(
            request,
            "partials/packages/error.html",
            {"error": f"Failed to list installed packages: {str(e)}"},
        )


@router.post("/install", response_class=HTMLResponse)
async def install_packages(
    request: Request,
    templates: TemplatesDep,
    package_service: PackageManagerServiceDep,
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Install selected packages."""

    try:
        form_data = await request.form()
        packages = []

        # Get packages from form data
        for key, value in form_data.items():
            if key.startswith("package_") and value:
                package_value = value if isinstance(value, str) else ""
                if package_value:
                    packages.append(package_value)

        if not packages:
            return templates.TemplateResponse(
                request,
                "partials/packages/install_error.html",
                {"error": "No packages selected for installation"},
            )

        success, message = await package_service.install_packages(packages)

        if success:
            return templates.TemplateResponse(
                request,
                "partials/packages/install_success.html",
                {"message": message, "packages": packages},
            )
        else:
            return templates.TemplateResponse(
                request, "partials/packages/install_error.html", {"error": message}
            )

    except Exception as e:
        logger.error(f"Error installing packages: {e}")
        return templates.TemplateResponse(
            request,
            "partials/packages/install_error.html",
            {"error": f"Installation failed: {str(e)}"},
        )


@router.post("/remove", response_class=HTMLResponse)
async def remove_packages(
    request: Request,
    templates: TemplatesDep,
    package_service: PackageManagerServiceDep,
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Remove selected packages."""

    try:
        form_data = await request.form()
        packages = []

        # Get packages from form data
        for key, value in form_data.items():
            if key.startswith("remove_package_") and value:
                package_value = value if isinstance(value, str) else ""
                if package_value:
                    packages.append(package_value)

        if not packages:
            return templates.TemplateResponse(
                request,
                "partials/packages/remove_error.html",
                {"error": "No packages selected for removal"},
            )

        success, message = await package_service.remove_packages(packages)

        if success:
            return templates.TemplateResponse(
                request,
                "partials/packages/remove_success.html",
                {"message": message, "packages": packages},
            )
        else:
            return templates.TemplateResponse(
                request, "partials/packages/remove_error.html", {"error": message}
            )

    except Exception as e:
        logger.error(f"Error removing packages: {e}")
        return templates.TemplateResponse(
            request,
            "partials/packages/remove_error.html",
            {"error": f"Removal failed: {str(e)}"},
        )


@router.get("/{package_name}/info", response_class=HTMLResponse)
async def get_package_info(
    package_name: str,
    request: Request,
    templates: TemplatesDep,
    package_service: PackageManagerServiceDep,
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Get detailed information about a specific package."""

    try:
        package_info = await package_service.get_package_info(package_name)

        if not package_info:
            raise HTTPException(status_code=404, detail="Package not found")

        return templates.TemplateResponse(
            request, "partials/packages/package_info.html", {"package": package_info}
        )

    except ValueError as e:
        return templates.TemplateResponse(
            request, "partials/packages/error.html", {"error": str(e)}, status_code=400
        )
    except Exception as e:
        logger.error(f"Error getting package info for {package_name}: {e}")
        return templates.TemplateResponse(
            request,
            "partials/packages/error.html",
            {"error": f"Failed to get package info: {str(e)}"},
            status_code=500,
        )
