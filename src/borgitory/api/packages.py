"""
Package Management API endpoints.
Provides functionality to search, install, and manage Debian packages.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Form
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

    form_data = (
        await request.form() if request.method == "POST" else request.query_params
    )

    query = ""
    for param_name in form_data.keys():
        if param_name in ["package_search", "package_name", "search"]:
            value = form_data[param_name]
            query = value if isinstance(value, str) else ""
            break

    if not query or len(query) < 2:
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

        target_input = request.headers.get("hx-target-input", "package-search")

        return templates.TemplateResponse(
            request,
            "partials/packages/search_results.html",
            {"packages": packages, "query": query, "input_id": target_input},
        )

    except Exception as e:
        logger.error(f"Error searching packages: {e}")

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
        packages = await package_service.list_installed_packages()

        user_packages = package_service.get_user_installed_packages()
        user_package_names = {pkg.package_name for pkg in user_packages}

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

        for key, value in form_data.items():
            if key.startswith("selected_package_") and value:
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
            # Return success message with HX-Trigger to clear selections
            response = templates.TemplateResponse(
                request,
                "partials/packages/install_success.html",
                {"message": message, "packages": packages},
            )
            response.headers["HX-Trigger"] = "clear-selections"
            return response
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


@router.post("/select", response_class=HTMLResponse)
async def select_package(
    request: Request,
    templates: TemplatesDep,
    current_user: User = Depends(get_current_user),
    package_name: str = Form(...),
) -> _TemplateResponse:
    """Add a package to the selection state."""
    try:
        # Get current selections from form data if present
        form_data = await request.form()
        selected_packages = []

        # Extract existing selections from hidden fields
        for key, value in form_data.items():
            if key.startswith("selected_package_"):
                selected_packages.append(value)

        # Add new package if not already selected
        if package_name not in selected_packages:
            selected_packages.append(package_name)

        return templates.TemplateResponse(
            request,
            "partials/packages/selected_packages.html",
            {"selected_packages": selected_packages},
        )

    except Exception as e:
        logger.error(f"Error selecting package: {e}")
        return templates.TemplateResponse(
            request,
            "partials/packages/error.html",
            {"error": f"Failed to select package: {str(e)}"},
        )


@router.post("/remove-selection", response_class=HTMLResponse)
async def remove_package_selection(
    request: Request,
    templates: TemplatesDep,
    current_user: User = Depends(get_current_user),
    package_name: str = Form(...),
) -> _TemplateResponse:
    """Remove a package from the selection state."""
    try:
        # Get current selections from form data
        form_data = await request.form()
        selected_packages = []

        # Extract existing selections from hidden fields
        for key, value in form_data.items():
            if key.startswith("selected_package_"):
                selected_packages.append(value)

        # Remove the specified package
        if package_name in selected_packages:
            selected_packages.remove(package_name)

        return templates.TemplateResponse(
            request,
            "partials/packages/selected_packages.html",
            {"selected_packages": selected_packages},
        )

    except Exception as e:
        logger.error(f"Error removing package selection: {e}")
        return templates.TemplateResponse(
            request,
            "partials/packages/error.html",
            {"error": f"Failed to remove package: {str(e)}"},
        )


@router.get("/clear-selections", response_class=HTMLResponse)
async def clear_package_selections(
    request: Request,
    templates: TemplatesDep,
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Clear all package selections."""
    return templates.TemplateResponse(
        request,
        "partials/packages/selected_packages.html",
        {"selected_packages": []},
    )
