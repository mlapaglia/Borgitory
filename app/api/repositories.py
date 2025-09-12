import logging
from typing import List, Annotated
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Form,
    File,
    UploadFile,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import Repository, User, get_db
from app.models.schemas import (
    Repository as RepositorySchema,
    RepositoryCreate,
    RepositoryUpdate,
)
from app.dependencies import BorgServiceDep, SchedulerServiceDep, VolumeServiceDep
from app.api.auth import get_current_user
from app.dependencies_services import RepositoryServiceDep
from app.dependencies_clean import RepositoryQueryDep
from app.services.interfaces import RepositoryService, RepositoryQueryService, RepositoryNotFoundError, RepositoryValidationError, RepositoryError
from app.utils.secure_path import (
    PathSecurityError,
    user_secure_exists,
    user_secure_isdir,
    user_get_directory_listing,
)

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

@router.post("/")
async def create_repository(
    request: Request,
    repo: RepositoryCreate,
    repository_service: RepositoryService = RepositoryServiceDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_htmx_request = "hx-request" in request.headers

    try:
        repository = await repository_service.create_repository(
            name=repo.name,
            path=repo.path,
            passphrase=repo.passphrase,
            user=current_user,
            db=db,
            is_import=False
        )

        # Success response
        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/repositories/form_create_success.html",
                {"repository_name": repository.name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            return repository

    except RepositoryValidationError as e:
        error_msg = str(e)
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_create_error.html",
                {"error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=400, detail=error_msg)
        
    except RepositoryError as e:
        error_msg = str(e)
        logger.error(f"Repository creation failed: {error_msg}")
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_create_error.html",
                {"error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[RepositorySchema])
def list_repositories(
    repository_query: RepositoryQueryDep,
    db: Annotated[Session, Depends(get_db)],
    skip: int = 0, 
    limit: int = 100
):
    """
    List repositories using clean FastAPI DI pattern.
    
    PROOF OF CONCEPT: This endpoint demonstrates proper FastAPI dependency injection
    - Service injected via Annotated[Type, Depends()] pattern
    - Business logic isolated in service layer
    - Easy to test with app.dependency_overrides
    """
    return repository_query.list_repositories(db, skip, limit)


@router.get("/scan")
async def scan_repositories(request: Request, borg_svc: BorgServiceDep):
    """Scan for existing repositories and return HTML for HTMX"""
    try:
        available_repos = await borg_svc.scan_for_repositories()

        accept_header = request.headers.get("Accept", "")
        if "application/json" in accept_header or "hx-request" not in request.headers:
            return {"repositories": available_repos}

        return templates.TemplateResponse(
            request,
            "partials/repositories/scan_results.html",
            {"repositories": available_repos},
        )
    except Exception as e:
        logger.error(f"Error scanning for repositories: {e}")

        if "hx-request" in request.headers:
            return templates.TemplateResponse(
                request,
                "partials/common/error_message.html",
                {"error_message": f"Error: {str(e)}"},
            )
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to scan repositories: {str(e)}"
            )


@router.get("/html", response_class=HTMLResponse)
def get_repositories_html(request: Request, db: Session = Depends(get_db)):
    """Get repositories as HTML for frontend display"""
    try:
        repositories = db.query(Repository).all()
        return templates.TemplateResponse(
            request,
            "partials/repositories/list_content.html",
            {"repositories": repositories},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {
                "error_message": f"Error loading repositories: {str(e)}",
            },
        )


@router.get("/directories")
async def list_directories(volume_svc: VolumeServiceDep, path: str = "/mnt"):
    """List directories at the given path for autocomplete functionality. All paths must be under /mnt."""

    try:
        if not user_secure_exists(path):
            return {"directories": []}

        if not user_secure_isdir(path):
            return {"directories": []}

        directories = user_get_directory_listing(path, include_files=False)

        return {"directories": directories}

    except PathSecurityError as e:
        logger.warning(f"Path security violation: {e}")
        return {"directories": []}

    except Exception as e:
        logger.error(f"Error listing directories at {path}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list directories: {str(e)}"
        )


@router.get("/import-form-update", response_class=HTMLResponse)
async def update_import_form(
    request: Request, borg_svc: BorgServiceDep, path: str = "", loading: str = ""
):
    """Update import form fields based on selected repository path"""

    if not path:
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_dynamic.html",
            {
                "path": "",
                "show_encryption_info": False,
                "show_passphrase": False,
                "show_keyfile": False,
                "enable_submit": False,
                "preview": "",
            },
        )

    if loading == "true":
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_loading.html",
            {
                "path": path,
            },
        )

    try:
        available_repos = await borg_svc.scan_for_repositories()
        selected_repo = None

        for repo in available_repos:
            if repo.get("path") == path:
                selected_repo = repo
                break

        if not selected_repo:
            logger.warning(f"Repository not found for path: {path}")
            return templates.TemplateResponse(
                request,
                "partials/repositories/import_form_dynamic.html",
                {
                    "path": path,
                    "show_encryption_info": True,
                    "show_passphrase": True,
                    "show_keyfile": True,
                    "enable_submit": True,
                    "preview": "Repository details not found - please re-scan",
                },
            )

        encryption_mode = selected_repo.get("encryption_mode", "unknown")
        requires_keyfile = selected_repo.get("requires_keyfile", False)
        preview = selected_repo.get("preview", f"Encryption: {encryption_mode}")

        show_passphrase = encryption_mode != "none"
        show_keyfile = requires_keyfile

        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_simple.html",
            {
                "path": path,
                "show_passphrase": show_passphrase,
                "show_keyfile": show_keyfile,
                "preview": preview,
            },
        )

    except Exception as e:
        logger.error(f"Error updating import form: {e}")
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_simple.html",
            {
                "path": path,
                "show_passphrase": True,
                "show_keyfile": True,
                "preview": "Error loading repository details",
            },
        )


@router.get("/import-form", response_class=HTMLResponse)
async def get_import_form(request: Request):
    """Get the import repository form"""
    return templates.TemplateResponse(request, "partials/repositories/form_import.html")


@router.get("/create-form", response_class=HTMLResponse)
async def get_create_form(request: Request):
    """Get the create repository form"""
    return templates.TemplateResponse(request, "partials/repositories/form_create.html")


@router.post("/import")
async def import_repository(
    request: Request,
    repository_service: RepositoryService = RepositoryServiceDep,
    name: str = Form(...),
    path: str = Form(...),
    passphrase: str = Form(...),
    keyfile: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    is_htmx_request = "hx-request" in request.headers

    try:
        keyfile_content = None
        keyfile_filename = None
        if keyfile and keyfile.filename:
            keyfile_content = await keyfile.read()
            keyfile_filename = keyfile.filename

        repository = await repository_service.create_repository(
            name=name,
            path=path,
            passphrase=passphrase,
            user=None,  # Import doesn't require auth currently
            db=db,
            is_import=True,
            keyfile_content=keyfile_content,
            keyfile_filename=keyfile_filename
        )

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/repositories/form_import_success.html",
                {"repository_name": repository.name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            return repository

    except RepositoryValidationError as e:
        error_msg = str(e)
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_import_error.html",
                {"error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=400, detail=error_msg)
        
    except RepositoryError as e:
        error_msg = str(e)
        logger.error(f"Repository import failed: {error_msg}")
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_import_error.html",
                {"error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/import-form-update", response_class=HTMLResponse)
async def update_import_form(
    request: Request, borg_svc: BorgServiceDep, path: str = "", loading: str = ""
):
    """Update import form fields based on selected repository path"""

    if not path:
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_dynamic.html",
            {
                "path": "",
                "show_encryption_info": False,
                "show_passphrase": False,
                "show_keyfile": False,
                "enable_submit": False,
                "preview": "",
            },
        )

    if loading == "true":
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_loading.html",
            {
                "path": path,
            },
        )

    try:
        available_repos = await borg_svc.scan_for_repositories()
        selected_repo = None

        for repo in available_repos:
            if repo.get("path") == path:
                selected_repo = repo
                break

        if not selected_repo:
            logger.warning(f"Repository not found for path: {path}")
            return templates.TemplateResponse(
                request,
                "partials/repositories/import_form_dynamic.html",
                {
                    "path": path,
                    "show_encryption_info": True,
                    "show_passphrase": True,
                    "show_keyfile": True,
                    "enable_submit": True,
                    "preview": "Repository details not found - please re-scan",
                },
            )

        encryption_mode = selected_repo.get("encryption_mode", "unknown")
        requires_keyfile = selected_repo.get("requires_keyfile", False)
        preview = selected_repo.get("preview", f"Encryption: {encryption_mode}")

        show_passphrase = encryption_mode != "none"
        show_keyfile = requires_keyfile

        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_simple.html",
            {
                "path": path,
                "show_passphrase": show_passphrase,
                "show_keyfile": show_keyfile,
                "preview": preview,
            },
        )

    except Exception as e:
        logger.error(f"Error updating import form: {e}")
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_simple.html",
            {
                "path": path,
                "show_passphrase": True,
                "show_keyfile": True,
                "preview": "Error loading repository details",
            },
        )


@router.get("/{repo_id}", response_model=RepositorySchema)
def get_repository(
    repo_id: int, 
    repository_service: RepositoryService = RepositoryServiceDep,
    db: Session = Depends(get_db)
):
    repository = repository_service.get_repository(repo_id, db)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.put("/{repo_id}", response_model=RepositorySchema)
async def update_repository(
    repo_id: int, 
    repo_update: RepositoryUpdate, 
    repository_service: RepositoryService = RepositoryServiceDep,
    db: Session = Depends(get_db)
):
    try:
        update_data = repo_update.model_dump(exclude_unset=True)
        # Note: Using None for user to maintain backward compatibility
        # Authentication can be added as a separate security improvement
        repository = await repository_service.update_repository(
            repo_id=repo_id,
            updates=update_data,
            user=None,
            db=db
        )
        return repository
        
    except RepositoryNotFoundError:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    except RepositoryValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{repo_id}", response_class=HTMLResponse)
async def delete_repository(
    repo_id: int,
    request: Request,
    scheduler_svc: SchedulerServiceDep,
    delete_borg_repo: bool = False,
    repository_service: RepositoryService = RepositoryServiceDep,
    db: Session = Depends(get_db),
):
    try:
        await repository_service.delete_repository(
            repo_id=repo_id,
            user=None,  # No auth required currently
            db=db,
            scheduler_service=scheduler_svc,
            delete_borg_repo=delete_borg_repo
        )

        return get_repositories_html(request, db)
        
    except RepositoryNotFoundError:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    except RepositoryValidationError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{repo_id}/archives")
async def list_archives(
    request: Request,
    repo_id: int,
    borg_svc: BorgServiceDep,
    db: Session = Depends(get_db),
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        archives = await borg_svc.list_archives(repository)

        recent_archives = archives[:10] if len(archives) > 10 else archives
        return templates.TemplateResponse(
            request,
            "partials/archives/list_content.html",
            {
                "repository": repository,
                "archives": archives,
                "recent_archives": recent_archives,
            },
        )
    except Exception as e:
        logger.error(f"Error listing archives for repository {repo_id}: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": f"Error loading archives: {str(e)}"},
        )


@router.get("/{repo_id}/archives/html", response_class=HTMLResponse)
async def list_archives_html(
    repo_id: int,
    request: Request,
    borg_svc: BorgServiceDep,
    db: Session = Depends(get_db),
):
    """Get repository archives as HTML"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")

        try:
            archives = await borg_svc.list_archives(repository)

            processed_archives = []

            if archives:
                recent_archives = archives[-10:] if len(archives) > 10 else archives
                recent_archives.reverse()

                for archive in recent_archives:
                    archive_name = archive.get("name", "Unknown")
                    archive_time = archive.get("time", "")

                    formatted_time = archive_time
                    if archive_time:
                        try:
                            from datetime import datetime

                            dt = datetime.fromisoformat(
                                archive_time.replace("Z", "+00:00")
                            )
                            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError):
                            pass

                    size_info = ""
                    if "stats" in archive:
                        stats = archive["stats"]
                        if "original_size" in stats:
                            size_bytes = stats["original_size"]
                            for unit in ["B", "KB", "MB", "GB", "TB"]:
                                if size_bytes < 1024.0:
                                    size_info = f"{size_bytes:.1f} {unit}"
                                    break
                                size_bytes /= 1024.0

                    processed_archives.append(
                        {
                            "name": archive_name,
                            "formatted_time": formatted_time,
                            "size_info": size_info,
                        }
                    )

            return templates.TemplateResponse(
                request,
                "partials/archives/list_content.html",
                {
                    "repository": repository,
                    "archives": archives,
                    "recent_archives": processed_archives,
                },
            )

        except Exception as e:
            logger.error(f"Error listing archives for repository {repo_id}: {e}")
            return templates.TemplateResponse(
                request,
                "partials/archives/error_message.html",
                {
                    "error_message": str(e),
                    "show_help": True,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_archives_html: {e}")
        return templates.TemplateResponse(
            request,
            "partials/archives/error_message.html",
            {
                "error_message": "An unexpected error occurred while loading archives.",
                "show_help": False,
            },
        )


@router.get("/archives/selector")
async def get_archives_repository_selector(
    request: Request, db: Session = Depends(get_db)
):
    """Get repository selector for archives with repositories populated"""
    repositories = db.query(Repository).all()

    return templates.TemplateResponse(
        request,
        "partials/archives/repository_selector.html",
        {"repositories": repositories},
    )


@router.get("/archives/loading")
async def get_archives_loading(request: Request):
    """Get loading state for archives"""
    return templates.TemplateResponse(
        request, "partials/archives/loading_state.html", {}
    )


@router.post("/archives/load-with-spinner")
async def load_archives_with_spinner(request: Request, repository_id: str = Form("")):
    """Show loading spinner then trigger loading actual archives"""
    if not repository_id or repository_id == "":
        return templates.TemplateResponse(
            request, "partials/archives/empty_state.html", {}
        )

    try:
        repo_id = int(repository_id)
        return templates.TemplateResponse(
            request,
            "partials/archives/loading_with_trigger.html",
            {"repository_id": repo_id},
        )
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            request, "partials/archives/empty_state.html", {}
        )


@router.get("/archives/list")
async def get_archives_list(
    request: Request,
    borg_svc: BorgServiceDep,
    repository_id: str = "",
    db: Session = Depends(get_db),
):
    """Get archives list or empty state"""
    if not repository_id or repository_id == "":
        return templates.TemplateResponse(
            request, "partials/archives/empty_state.html", {}
        )

    try:
        repo_id = int(repository_id)
        return await list_archives_html(repo_id, request, borg_svc, db)
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            request, "partials/archives/empty_state.html", {}
        )


@router.get("/{repo_id}/info")
async def get_repository_info(
    repo_id: int, borg_svc: BorgServiceDep, db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        info = await borg_svc.get_repo_info(repository)
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{repo_id}/archives/{archive_name}/contents/load-with-spinner")
async def load_archive_contents_with_spinner(
    request: Request,
    repo_id: int,
    archive_name: str,
    path: str = Form(""),
    db: Session = Depends(get_db),
):
    """Show loading spinner then trigger loading actual directory contents"""
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    return templates.TemplateResponse(
        request,
        "partials/archives/directory_loading_with_trigger.html",
        {"repository_id": repo_id, "archive_name": archive_name, "path": path},
    )


@router.get("/{repo_id}/archives/{archive_name}/contents")
async def get_archive_contents(
    request: Request,
    repo_id: int,
    archive_name: str,
    borg_svc: BorgServiceDep,
    path: str = "",
    db: Session = Depends(get_db),
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        contents = await borg_svc.list_archive_directory_contents(
            repository, archive_name, path
        )

        return templates.TemplateResponse(
            request,
            "partials/archives/directory_contents.html",
            {
                "repository": repository,
                "archive_name": archive_name,
                "path": path,
                "items": contents,
                "breadcrumb_parts": path.split("/") if path else [],
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": f"Error loading directory contents: {str(e)}"},
        )


@router.get("/{repo_id}/archives/{archive_name}/extract")
async def extract_file(
    repo_id: int,
    archive_name: str,
    file: str,
    borg_svc: BorgServiceDep,
    db: Session = Depends(get_db),
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        return await borg_svc.extract_file_stream(repository, archive_name, file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
