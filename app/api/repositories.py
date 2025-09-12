import logging
import os
from typing import List
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
from app.utils.secure_path import (
    create_secure_filename,
    secure_path_join,
    secure_exists,
    secure_isdir,
    secure_remove_file,
    get_directory_listing,
    validate_path_within_base,
    PathSecurityError,
)

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


# Legacy functions replaced by secure_path utilities


@router.post("/")
async def create_repository(
    request: Request,
    repo: RepositoryCreate,
    borg_svc: BorgServiceDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_htmx_request = "hx-request" in request.headers

    try:
        # Check for duplicate name
        db_repo = db.query(Repository).filter(Repository.name == repo.name).first()
        if db_repo:
            error_msg = "Repository with this name already exists"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_create_error.html",
                    {"error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        # Check for duplicate path
        db_repo_path = db.query(Repository).filter(Repository.path == repo.path).first()
        if db_repo_path:
            error_msg = f"Repository with path '{repo.path}' already exists with name '{db_repo_path.name}'"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_create_error.html",
                    {"error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        # Create repository object but don't save to database yet
        db_repo = Repository(name=repo.name, path=repo.path)
        db_repo.set_passphrase(repo.passphrase)

        # Try to initialize the Borg repository first
        try:
            init_result = await borg_svc.initialize_repository(db_repo)
            if not init_result["success"]:
                # Initialization failed, don't save to database
                borg_error = init_result["message"]

                # Make error message more user-friendly
                if "Read-only file system" in borg_error:
                    error_msg = "Cannot create repository: The target directory is read-only. Please choose a writable location."
                elif "Permission denied" in borg_error:
                    error_msg = "Cannot create repository: Permission denied. Please check directory permissions."
                elif "already exists" in borg_error.lower():
                    error_msg = "A repository already exists at this location."
                else:
                    error_msg = f"Failed to initialize repository: {borg_error}"

                logger.error(
                    f"Repository initialization failed for '{repo.name}': {borg_error}"
                )
                if is_htmx_request:
                    return templates.TemplateResponse(
                        request,
                        "partials/repositories/form_create_error.html",
                        {"error_message": error_msg},
                        status_code=200,
                    )
                raise HTTPException(status_code=400, detail=error_msg)

        except Exception as init_error:
            # Initialization threw an exception, don't save to database
            error_msg = f"Failed to initialize repository: {str(init_error)}"
            logger.error(error_msg)
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_create_error.html",
                    {"error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=500, detail=error_msg)

        # Initialization succeeded, now save to database
        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)

        logger.info(f"Successfully created and initialized repository '{repo.name}')")

        # Success response
        if is_htmx_request:
            # Trigger repository list update and return success trigger
            response = templates.TemplateResponse(
                request,
                "partials/repositories/form_create_success.html",
                {"repository_name": repo.name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            # Return JSON for non-HTMX requests
            return db_repo

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_create_error.html",
                {"error_message": str(e.detail)},
                status_code=200,
            )
        raise
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to create repository: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_create_error.html",
                {"error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[RepositorySchema])
def list_repositories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    repositories = db.query(Repository).offset(skip).limit(limit).all()
    return repositories


@router.get("/scan")
async def scan_repositories(request: Request, borg_svc: BorgServiceDep):
    """Scan for existing repositories and return HTML for HTMX"""
    try:
        available_repos = await borg_svc.scan_for_repositories()

        # Check if request wants JSON (for backward compatibility)
        accept_header = request.headers.get("Accept", "")
        if "application/json" in accept_header or "hx-request" not in request.headers:
            return {"repositories": available_repos}

        # Return HTML for HTMX
        return templates.TemplateResponse(
            request,
            "partials/repositories/scan_results.html",
            {"repositories": available_repos},
        )
    except Exception as e:
        logger.error(f"Error scanning for repositories: {e}")

        # Check if this is an HTMX request
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
async def list_directories(volume_svc: VolumeServiceDep, path: str = "/repos"):
    """List directories at the given path for autocomplete functionality"""
    try:
        mounted_volumes = await volume_svc.get_mounted_volumes()

        allowed = path == "/"
        if not allowed:
            for volume in mounted_volumes:
                if path.startswith(volume):
                    allowed = True
                    break

        if not allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Path must be root directory or under one of the mounted volumes: {', '.join(mounted_volumes)}",
            )

        # Use secure path operations
        try:
            # Validate path is within allowed directories
            allowed_base_dirs = ["/"] + mounted_volumes if mounted_volumes else ["/"]

            # Normalize the path using secure validation
            validated_path = validate_path_within_base(path, "/")

            # Check if path exists and is a directory using secure functions
            if not secure_exists(validated_path, allowed_base_dirs):
                return {"directories": []}

            if not secure_isdir(validated_path, allowed_base_dirs):
                return {"directories": []}

            # Get directory listing using secure function
            directories = get_directory_listing(
                validated_path, allowed_base_dirs, include_files=False
            )

            # For root directory, filter out system directories
            if path == "/":
                ignored_dirs = {
                    "opt",
                    "home",
                    "usr",
                    "var",
                    "bin",
                    "sbin",
                    "lib",
                    "lib64",
                    "etc",
                    "proc",
                    "sys",
                    "dev",
                    "run",
                    "tmp",
                    "boot",
                    "mnt",
                    "media",
                    "srv",
                    "root",
                }
                directories = [d for d in directories if d["name"] not in ignored_dirs]

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
        # No repository selected - show disabled state
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

    # If loading=true, return loading template immediately
    if loading == "true":
        return templates.TemplateResponse(
            request,
            "partials/repositories/import_form_loading.html",
            {
                "path": path,
            },
        )

    try:
        # Look up repository details by path
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

        # Determine which fields to show
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
    borg_svc: BorgServiceDep,
    name: str = Form(...),
    path: str = Form(...),
    passphrase: str = Form(...),
    keyfile: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """Import an existing Borg repository"""
    is_htmx_request = "hx-request" in request.headers

    try:
        db_repo = db.query(Repository).filter(Repository.name == name).first()
        if db_repo:
            error_msg = "Repository with this name already exists"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_import_error.html",
                    {"error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        db_repo_path = db.query(Repository).filter(Repository.path == path).first()
        if db_repo_path:
            error_msg = f"Repository with path '{path}' already exists with name '{db_repo_path.name}'"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/repositories/form_import_error.html",
                    {"error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        keyfile_path = None
        if keyfile and keyfile.filename:
            keyfiles_dir = "/app/data/keyfiles"
            os.makedirs(keyfiles_dir, exist_ok=True)

            try:
                safe_filename = create_secure_filename(
                    name, keyfile.filename, add_uuid=True
                )
                keyfile_path = secure_path_join(keyfiles_dir, safe_filename)

                with open(keyfile_path, "wb") as f:
                    content = await keyfile.read()
                    f.write(content)

                logger.info(f"Saved keyfile for repository '{name}' at {keyfile_path}")
            except (PathSecurityError, OSError) as e:
                error_msg = f"Failed to save keyfile: {str(e)}"
                logger.error(error_msg)
                if is_htmx_request:
                    return templates.TemplateResponse(
                        request,
                        "partials/repositories/form_import_error.html",
                        {"error_message": error_msg},
                        status_code=200,
                    )
                raise HTTPException(status_code=400, detail=error_msg)

        db_repo = Repository(name=name, path=path)
        db_repo.set_passphrase(passphrase)

        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)

        verification_successful = await borg_svc.verify_repository_access(
            repo_path=path, passphrase=passphrase, keyfile_path=keyfile_path
        )

        if not verification_successful:
            if keyfile_path:
                secure_remove_file(keyfile_path, ["/app/data/keyfiles"])
            db.delete(db_repo)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Failed to verify repository access. Please check the path, passphrase, and keyfile (if required).",
            )

        try:
            archives = await borg_svc.list_archives(db_repo)
            logger.info(
                f"Successfully imported repository '{name}' with {len(archives)} archives"
            )
        except Exception:
            logger.info(
                f"Successfully imported repository '{name}' (could not count archives)"
            )

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/repositories/form_import_success.html",
                {"repository_name": name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            return db_repo

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_import_error.html",
                {"error_message": str(e.detail)},
                status_code=200,
            )
        raise
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to import repository: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/repositories/form_import_error.html",
                {"error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/{repo_id}", response_model=RepositorySchema)
def get_repository(repo_id: int, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.put("/{repo_id}", response_model=RepositorySchema)
def update_repository(
    repo_id: int, repo_update: RepositoryUpdate, db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    update_data = repo_update.model_dump(exclude_unset=True)

    if "passphrase" in update_data:
        repository.set_passphrase(update_data.pop("passphrase"))

    for field, value in update_data.items():
        setattr(repository, field, value)

    db.commit()
    db.refresh(repository)
    return repository


@router.delete("/{repo_id}", response_class=HTMLResponse)
async def delete_repository(
    repo_id: int,
    request: Request,
    scheduler_svc: SchedulerServiceDep,
    delete_borg_repo: bool = False,
    db: Session = Depends(get_db),
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    repo_name = repository.name

    from app.models.database import Job, Schedule

    active_jobs = (
        db.query(Job)
        .filter(
            Job.repository_id == repo_id,
            Job.status.in_(["running", "pending", "queued"]),
        )
        .all()
    )

    if active_jobs:
        active_job_types = [job.type for job in active_jobs]
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete repository '{repo_name}' - {len(active_jobs)} active job(s) running: {', '.join(active_job_types)}. Please wait for jobs to complete or cancel them first.",
        )

    schedules_to_delete = (
        db.query(Schedule).filter(Schedule.repository_id == repo_id).all()
    )

    for schedule in schedules_to_delete:
        try:
            await scheduler_svc.remove_schedule(schedule.id)
            logger.info(f"Removed scheduled job for schedule ID {schedule.id}")
        except Exception as e:
            logger.warning(
                f"Could not remove scheduled job for schedule ID {schedule.id}: {e}"
            )

    db.delete(repository)
    db.commit()

    return get_repositories_html(request, db)


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
