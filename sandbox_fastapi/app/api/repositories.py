"""
Clean repository API endpoint demonstrating proper FastAPI dependency injection.

This shows how much simpler endpoints become with proper service layer
and clean dependency injection following 2024 best practices.
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Request, Query, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import Field

from app.models.schemas import RepositoryImport, ImportResult, RepositoryResponse, RepositoryCreate
from app.dependencies import (
    RepositoryImportServiceDep, 
    RepositoryManagementServiceDep,
    RepositoryQueryServiceDep,
    DatabaseDep,
    TemplatesDep
)
from app.services.interfaces import RepositoryValidationError
from app.models.schemas import RepositoryScanResult, ValidationResult

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/import", response_class=HTMLResponse)
async def import_repository(
    request: Request,
    templates: TemplatesDep,
    import_service: RepositoryImportServiceDep,
    query_service: RepositoryQueryServiceDep,
    db: DatabaseDep,
    name: str = Form(...),
    path: str = Form(...),
    passphrase: str = Form(...),
    keyfile: UploadFile = File(None)
):
    """
    Import repository returning HTML fragment for HTMX.
    
    HTMX PRINCIPLE: Returns HTML, never JSON.
    """
    try:
        # Handle keyfile upload
        keyfile_content = None
        if keyfile and keyfile.filename:
            keyfile_content = await keyfile.read()
        
        # Validate repository first
        validation = await query_service.validate_repository_import(
            path, passphrase, keyfile_content
        )
        
        if not validation.is_valid:
            return templates.TemplateResponse(
                request,
                "partials/repositories/import_error.html",
                {"error_message": validation.message}
            )
        
        # Import repository
        from app.models.schemas import RepositoryImport
        import_data = RepositoryImport(name=name, path=path, passphrase=passphrase)
        result = await import_service.import_repository(import_data, db)
        
        if result.success:
            response = templates.TemplateResponse(
                request,
                "partials/repositories/import_success.html",
                {"repository": result.repository, "message": result.message}
            )
            # Trigger repository list refresh
            response.headers["HX-Trigger"] = "repositoryImported"
            return response
        else:
            return templates.TemplateResponse(
                request,
                "partials/repositories/import_error.html", 
                {"error_message": result.message}
            )
        
    except Exception as e:
        logger.error(f"Repository import error: {e}")
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_error.html",
            {"error_message": f"Import failed: {str(e)}"}
        )


@router.get("/", response_class=HTMLResponse)
def list_repositories_html(
    request: Request,
    templates: TemplatesDep,
    repository_service: RepositoryManagementServiceDep,
    db: DatabaseDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    List repositories as HTML for HTMX.
    
    HTMX PRINCIPLE: Returns HTML template, never JSON.
    """
    try:
        repositories = repository_service.list_repositories(db, skip, limit)
        return templates.TemplateResponse(
            request,
            "partials/repositories/list_content.html",
            {"repositories": repositories}
        )
    except Exception as e:
        logger.error(f"Error listing repositories: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Failed to load repositories"}
        )


@router.get("/create-form", response_class=HTMLResponse)
def get_create_form(
    request: Request,
    templates: TemplatesDep,
    query_service: RepositoryQueryServiceDep
):
    """
    Get create repository form.
    
    HTMX PRINCIPLE: Returns HTML form for modal display.
    """
    return templates.TemplateResponse(
        request,
        "partials/repositories/form_create.html",
        {}
    )


@router.post("/create", response_class=HTMLResponse)
async def create_repository(
    request: Request,
    templates: TemplatesDep,
    repository_service: RepositoryManagementServiceDep,
    db: DatabaseDep,
    name: str = Form(...),
    path: str = Form(...),
    passphrase: str = Form(...)
):
    """
    Create repository returning HTML fragment for HTMX.
    
    HTMX PRINCIPLE: Returns HTML, never JSON.
    """
    try:
        from app.models.schemas import RepositoryCreate
        repository_data = RepositoryCreate(name=name, path=path, passphrase=passphrase)
        repository = repository_service.create_repository(db, repository_data)
        
        response = templates.TemplateResponse(
            request,
            "partials/repositories/create_success.html",
            {"repository": repository, "message": f"Repository '{repository.name}' created successfully"}
        )
        # Trigger repository list refresh
        response.headers["HX-Trigger"] = "repositoryCreated"
        return response
        
    except Exception as e:
        logger.error(f"Repository creation error: {e}")
        return templates.TemplateResponse(
            request,
            "partials/repositories/create_error.html",
            {"error_message": str(e)}
        )


@router.get("/scan", response_class=HTMLResponse)
async def scan_repositories(
    request: Request,
    templates: TemplatesDep,
    query_service: RepositoryQueryServiceDep,
    path: str = Query("/mnt", description="Path to scan for repositories")
):
    """
    Scan for existing repositories and return HTML for HTMX.
    
    HTMX PRINCIPLE: Synchronous operation with loading indicator.
    """
    try:
        repositories = await query_service.scan_repositories(path)
        
        return templates.TemplateResponse(
            request,
            "partials/repositories/scan_results.html",
            {"repositories": repositories, "scan_path": path}
        )
    except TimeoutError as e:
        logger.warning(f"Repository scan timed out: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Scan taking too long. Try a smaller directory or more specific path."}
        )
    except Exception as e:
        logger.error(f"Error scanning for repositories: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": f"Scan failed: {str(e)}"}
        )


@router.get("/import-form", response_class=HTMLResponse)
def get_import_form(
    request: Request,
    templates: TemplatesDep,
    path: str = Query("", description="Pre-filled repository path"),
    name: str = Query("", description="Pre-filled repository name"),
    encryption_mode: str = Query("", description="Repository encryption mode"),
    requires_keyfile: bool = Query(False, description="Whether repository requires keyfile"),
    preview: str = Query("", description="Repository preview information")
):
    """
    Get import repository form with optional pre-filled values.
    
    HTMX PRINCIPLE: Returns HTML form that adapts based on repository encryption.
    """
    # Generate suggested name if not provided
    if not name and path:
        name = path.split('/')[-1] or "Imported Repository"
    
    # Determine form state based on encryption
    show_encryption_info = encryption_mode and encryption_mode not in ['unencrypted', 'unknown', '']
    show_passphrase = encryption_mode and encryption_mode not in ['unencrypted', 'unknown', '']
    show_keyfile = requires_keyfile
    
    return templates.TemplateResponse(
        request,
        "partials/repositories/form_import_filled.html",
        {
            "path": path,
            "name": name,
            "encryption_mode": encryption_mode,
            "requires_keyfile": requires_keyfile,
            "preview": preview,
            "show_encryption_info": show_encryption_info,
            "show_passphrase": show_passphrase,
            "show_keyfile": show_keyfile
        }
    )


@router.post("/fill-import-form", response_class=HTMLResponse)
async def fill_import_form(
    request: Request,
    templates: TemplatesDep,
):
    """
    Fill import form fields based on selected repository data.
    
    HTMX PRINCIPLE: Returns only the form fields HTML to update within existing form.
    """
    form_data = await request.form()
    path = form_data.get("path", "")
    name = form_data.get("name", "")
    encryption_mode = form_data.get("encryption_mode", "")
    requires_keyfile = form_data.get("requires_keyfile", "false") == "true"
    preview = form_data.get("preview", "")
    
    # Generate suggested name if not provided
    if not name and path:
        name = path.split('/')[-1] or "Imported Repository"
    
    return templates.TemplateResponse(
        request,
        "partials/repositories/import_form_fields.html",
        {
            "path": path,
            "name": name,
            "encryption_mode": encryption_mode,
            "requires_keyfile": requires_keyfile,
            "preview": preview
        }
    )


@router.get("/directories", response_class=HTMLResponse)
@router.post("/directories", response_class=HTMLResponse)
async def list_directories(
    request: Request,
    templates: TemplatesDep,
    query_service: RepositoryQueryServiceDep,
    path: str = Query("/mnt", description="Path to list directories")
):
    """
    List directories for autocomplete functionality.
    
    HTMX PRINCIPLE: Returns HTML options for path autocomplete.
    Supports both GET (query param) and POST (form data) for HTMX flexibility.
    """
    try:
        # For POST requests, get path from form data
        if request.method == "POST":
            form_data = await request.form()
            path = form_data.get("path", "/mnt")
        
        # Only show dropdown if path looks like a directory (ends with /)
        if not path or not path.endswith('/'):
            return templates.TemplateResponse(
                request,
                "partials/repositories/directory_options.html",
                {"directories": [], "current_path": path, "show_dropdown": False}
            )
        
        directories = query_service.list_directories(path, include_files=False)
        
        return templates.TemplateResponse(
            request,
            "partials/repositories/directory_options.html",
            {"directories": directories, "current_path": path, "show_dropdown": True}
        )
    except Exception as e:
        logger.debug(f"Directory listing failed: {e}")
        return templates.TemplateResponse(
            request,
            "partials/repositories/directory_options.html",
            {"directories": [], "current_path": path, "show_dropdown": True}
        )


@router.post("/set-path", response_class=HTMLResponse)
async def set_directory_path(
    request: Request,
    templates: TemplatesDep
):
    """
    Set the selected directory path in the input field.
    
    HTMX PRINCIPLE: Returns HTML to update the input value and hide dropdown.
    """
    try:
        form_data = await request.form()
        selected_path = form_data.get("path", "")
        
        return templates.TemplateResponse(
            request,
            "partials/repositories/path_update.html",
            {"selected_path": selected_path}
        )
    except Exception as e:
        logger.error(f"Error setting path: {e}")
        return HTMLResponse("")


