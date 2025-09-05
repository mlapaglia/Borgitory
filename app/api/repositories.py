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
from app.services.borg_service import borg_service
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.post("/")
async def create_repository(
    request: Request,
    repo: RepositoryCreate,
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
                    "partials/repositories/form_create_error.html",
                    {"request": request, "error_message": error_msg},
                    status_code=400,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        # Check for duplicate path
        db_repo_path = db.query(Repository).filter(Repository.path == repo.path).first()
        if db_repo_path:
            error_msg = f"Repository with path '{repo.path}' already exists with name '{db_repo_path.name}'"
            if is_htmx_request:
                return templates.TemplateResponse(
                    "partials/repositories/form_create_error.html",
                    {"request": request, "error_message": error_msg},
                    status_code=400,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        db_repo = Repository(name=repo.name, path=repo.path)
        db_repo.set_passphrase(repo.passphrase)

        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)

        try:
            init_result = await borg_service.initialize_repository(db_repo)
            if not init_result["success"]:
                logger.warning(
                    f"Repository '{repo.name}' created in database but Borg initialization failed: {init_result['message']}"
                )
        except Exception as init_error:
            logger.error(
                f"Repository '{repo.name}' created in database but Borg initialization error: {init_error}"
            )

        # Success response
        if is_htmx_request:
            # Trigger repository list update and return fresh form
            response = templates.TemplateResponse(
                "partials/repositories/form_create_success.html",
                {"request": request, "repository_name": repo.name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            # Return JSON for non-HTMX requests
            return db_repo

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                "partials/repositories/form_create_error.html",
                {"request": request, "error_message": str(e.detail)},
                status_code=e.status_code,
            )
        raise
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to create repository: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                "partials/repositories/form_create_error.html",
                {"request": request, "error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[RepositorySchema])
def list_repositories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    repositories = db.query(Repository).offset(skip).limit(limit).all()
    return repositories


@router.get("/scan")
async def scan_repositories(request: Request):
    """Scan for existing repositories and return HTML for HTMX"""
    try:
        available_repos = await borg_service.scan_for_repositories()

        # Check if request wants JSON (for backward compatibility)
        accept_header = request.headers.get("Accept", "")
        if "application/json" in accept_header or "hx-request" not in request.headers:
            return {"repositories": available_repos}

        # Return HTML for HTMX
        return templates.TemplateResponse(
            "partials/repositories/scan_results.html",
            {"request": request, "repositories": available_repos},
        )
    except Exception as e:
        logger.error(f"Error scanning for repositories: {e}")

        # Check if this is an HTMX request
        if "hx-request" in request.headers:
            return templates.TemplateResponse(
                "partials/common/error_message.html",
                {"request": request, "error_message": f"Error: {str(e)}"}
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
            "partials/repositories/list_content.html",
            {"request": request, "repositories": repositories}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/common/error_message.html",
            {"request": request, "error_message": f"Error loading repositories: {str(e)}"}
        )


@router.get("/directories")
async def list_directories(path: str = "/repos"):
    """List directories at the given path for autocomplete functionality"""
    try:
        from app.services.volume_service import volume_service

        mounted_volumes = await volume_service.get_mounted_volumes()

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

        # Normalize path
        path = os.path.normpath(path)

        # Check if path exists and is a directory
        if not os.path.exists(path):
            return {"directories": []}

        if not os.path.isdir(path):
            return {"directories": []}

        directories = []
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    # For root directory, filter out system directories
                    if path == "/":
                        # Hardcoded list of root directories to ignore
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

                        if item not in ignored_dirs:
                            directories.append({"name": item, "path": item_path})
                    else:
                        directories.append({"name": item, "path": item_path})
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {path}")
            return {"directories": []}

        # Sort directories alphabetically
        directories.sort(key=lambda x: x["name"].lower())

        return {"directories": directories}

    except Exception as e:
        logger.error(f"Error listing directories at {path}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list directories: {str(e)}"
        )


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
    delete_borg_repo: bool = False,
    db: Session = Depends(get_db),
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    repo_name = repository.name

    # Check for active jobs before allowing deletion
    from app.models.database import Job, JobTask, Schedule

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

    # Count entities that will be deleted for reporting
    jobs_count = db.query(Job).filter(Job.repository_id == repo_id).count()
    tasks_count = (
        db.query(JobTask).join(Job).filter(Job.repository_id == repo_id).count()
    )
    schedules_to_delete = (
        db.query(Schedule).filter(Schedule.repository_id == repo_id).all()
    )
    schedules_count = len(schedules_to_delete)

    # Remove scheduled jobs from APScheduler before deleting from database
    from app.services.scheduler_service import scheduler_service

    for schedule in schedules_to_delete:
        try:
            await scheduler_service.remove_schedule(schedule.id)
            logger.info(f"Removed scheduled job for schedule ID {schedule.id}")
        except Exception as e:
            logger.warning(
                f"Could not remove scheduled job for schedule ID {schedule.id}: {e}"
            )

    # Delete the repository - this will cascade to jobs and schedules due to the
    # cascade="all, delete-orphan" relationships defined in the Repository model.
    # Jobs will then cascade to JobTask records as well.
    db.delete(repository)
    db.commit()

    # TODO: If delete_borg_repo is True, we could also delete the actual Borg repository
    # This would require careful implementation to avoid data loss

    # Return updated repository list HTML (HTMX way)
    return get_repositories_html(request, db)


@router.get("/{repo_id}/archives")
async def list_archives(repo_id: int, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        archives = await borg_service.list_archives(repository)
        return {"archives": archives}
    except Exception as e:
        logger.error(f"Error listing archives for repository {repo_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list archives: {str(e)}"
        )


@router.get("/{repo_id}/archives/html", response_class=HTMLResponse)
async def list_archives_html(
    repo_id: int, request: Request, db: Session = Depends(get_db)
):
    """Get repository archives as HTML"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")

        try:
            archives = await borg_service.list_archives(repository)

            # Process archives data for template
            processed_archives = []
            
            if archives:
                # Show most recent archives first (limit to 10)
                recent_archives = archives[-10:] if len(archives) > 10 else archives
                recent_archives.reverse()  # Most recent first

                for archive in recent_archives:
                    # Parse archive information
                    archive_name = archive.get("name", "Unknown")
                    archive_time = archive.get("time", "")

                    # Format the timestamp if available
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

                    # Archive size information
                    size_info = ""
                    if "stats" in archive:
                        stats = archive["stats"]
                        if "original_size" in stats:
                            # Convert bytes to human readable
                            size_bytes = stats["original_size"]
                            for unit in ["B", "KB", "MB", "GB", "TB"]:
                                if size_bytes < 1024.0:
                                    size_info = f"{size_bytes:.1f} {unit}"
                                    break
                                size_bytes /= 1024.0

                    processed_archives.append({
                        "name": archive_name,
                        "formatted_time": formatted_time,
                        "size_info": size_info,
                    })

            return templates.TemplateResponse(
                "partials/archives/list_content.html",
                {
                    "request": request,
                    "repository": repository,
                    "archives": archives,
                    "recent_archives": processed_archives,
                }
            )

        except Exception as e:
            logger.error(f"Error listing archives for repository {repo_id}: {e}")
            return templates.TemplateResponse(
                "partials/archives/error_message.html",
                {
                    "request": request,
                    "error_message": str(e),
                    "show_help": True,
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_archives_html: {e}")
        return templates.TemplateResponse(
            "partials/archives/error_message.html",
            {
                "request": request,
                "error_message": "An unexpected error occurred while loading archives.",
                "show_help": False,
            }
        )


@router.get("/archives/selector")
async def get_archives_repository_selector(
    request: Request, db: Session = Depends(get_db)
):
    """Get repository selector for archives with repositories populated"""
    repositories = db.query(Repository).all()

    return templates.TemplateResponse(
        "partials/archives/repository_selector.html",
        {"request": request, "repositories": repositories},
    )


@router.get("/archives/list")
async def get_archives_list(
    request: Request, repository_id: int = None, db: Session = Depends(get_db)
):
    """Get archives list or empty state"""
    if not repository_id:
        return templates.TemplateResponse(
            "partials/archives/empty_state.html", {"request": request}
        )

    # Redirect to the existing archives HTML endpoint
    return await list_archives_html(repository_id, request, db)


@router.get("/{repo_id}/info")
async def get_repository_info(repo_id: int, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        info = await borg_service.get_repo_info(repository)
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repo_id}/archives/{archive_name}/contents")
async def get_archive_contents(
    repo_id: int, archive_name: str, path: str = "", db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        contents = await borg_service.list_archive_directory_contents(
            repository, archive_name, path
        )
        return {"archive": archive_name, "path": path, "items": contents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repo_id}/archives/{archive_name}/extract")
async def extract_file(
    repo_id: int, archive_name: str, file: str, db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        return await borg_service.extract_file_stream(repository, archive_name, file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import-form-update", response_class=HTMLResponse)
def update_import_form(request: Request, repo_select: str = ""):
    """Update import form fields based on selected repository"""

    if not repo_select:
        # No repository selected - show disabled state
        return templates.TemplateResponse(
            "partials/repositories/import_form_dynamic.html",
            {
                "request": request,
                "path": "",
                "show_encryption_info": False,
                "show_passphrase": False,
                "show_keyfile": False,
                "enable_submit": False,
                "preview": "",
            }
        )

    try:
        import json

        repo_data = json.loads(repo_select)

        path = repo_data.get("path", "")
        encryption_mode = repo_data.get("encryption_mode", "unknown")
        requires_keyfile = repo_data.get("requires_keyfile", False)
        preview = repo_data.get("preview", f"Encryption: {encryption_mode}")

        # Determine which fields to show
        show_passphrase = encryption_mode != "none"
        show_keyfile = requires_keyfile
        show_encryption_info = True

        return templates.TemplateResponse(
            "partials/repositories/import_form_dynamic.html",
            {
                "request": request,
                "path": path,
                "show_encryption_info": show_encryption_info,
                "show_passphrase": show_passphrase,
                "show_keyfile": show_keyfile,
                "enable_submit": True,
                "preview": preview,
            }
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing repository selection: {e}")
        # Return disabled state on error
        return update_import_form(request, "")


@router.post("/import")
async def import_repository(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    passphrase: str = Form(...),
    keyfile: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """Import an existing Borg repository"""
    is_htmx_request = "hx-request" in request.headers

    try:
        # Check for duplicate name
        db_repo = db.query(Repository).filter(Repository.name == name).first()
        if db_repo:
            error_msg = "Repository with this name already exists"
            if is_htmx_request:
                return templates.TemplateResponse(
                    "partials/repositories/form_import_error.html",
                    {"request": request, "error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        # Check for duplicate path
        db_repo_path = db.query(Repository).filter(Repository.path == path).first()
        if db_repo_path:
            error_msg = f"Repository with path '{path}' already exists with name '{db_repo_path.name}'"
            if is_htmx_request:
                return templates.TemplateResponse(
                    "partials/repositories/form_import_error.html",
                    {"request": request, "error_message": error_msg},
                    status_code=200,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        # Handle keyfile if provided
        keyfile_path = None
        if keyfile and keyfile.filename:
            import os

            # Create keyfiles directory if it doesn't exist
            keyfiles_dir = "/app/data/keyfiles"
            os.makedirs(keyfiles_dir, exist_ok=True)

            # Save keyfile with a unique name
            keyfile_path = os.path.join(keyfiles_dir, f"{name}_{keyfile.filename}")
            with open(keyfile_path, "wb") as f:
                content = await keyfile.read()
                f.write(content)

            logger.info(f"Saved keyfile for repository '{name}' at {keyfile_path}")

        # Create repository record
        db_repo = Repository(name=name, path=path)
        db_repo.set_passphrase(passphrase)

        # Store keyfile path if we have one (we'll add this field later)
        # For now, let's just proceed with verification

        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)

        # Verify we can access the repository with the given credentials
        # This tests the user-provided credentials, not the stored ones
        verification_successful = await borg_service.verify_repository_access(
            repo_path=path, passphrase=passphrase, keyfile_path=keyfile_path
        )

        if not verification_successful:
            # If verification fails, remove the database entry and keyfile
            if keyfile_path and os.path.exists(keyfile_path):
                os.remove(keyfile_path)
            db.delete(db_repo)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Failed to verify repository access. Please check the path, passphrase, and keyfile (if required).",
            )

        # If verification passed, get archive count for logging
        try:
            archives = await borg_service.list_archives(db_repo)
            logger.info(
                f"Successfully imported repository '{name}' with {len(archives)} archives"
            )
        except Exception:
            logger.info(
                f"Successfully imported repository '{name}' (could not count archives)"
            )

        # Success response
        if is_htmx_request:
            # Trigger repository list update and return fresh form
            response = templates.TemplateResponse(
                "partials/repositories/form_import_success.html",
                {"request": request, "repository_name": name},
            )
            response.headers["HX-Trigger"] = "repositoryUpdate"
            return response
        else:
            # Return JSON for non-HTMX requests
            return db_repo

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                "partials/repositories/form_import_error.html",
                {"request": request, "error_message": str(e.detail)},
                status_code=200,
            )
        raise
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to import repository: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                "partials/repositories/form_import_error.html",
                {"request": request, "error_message": error_msg},
                status_code=200,
            )
        raise HTTPException(status_code=500, detail=error_msg)
