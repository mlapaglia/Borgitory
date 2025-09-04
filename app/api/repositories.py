import logging
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import Repository, User, get_db
from app.models.schemas import Repository as RepositorySchema, RepositoryCreate, RepositoryUpdate
from app.services.borg_service import borg_service
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.post("/", response_model=RepositorySchema, status_code=status.HTTP_201_CREATED)
async def create_repository(
    repo: RepositoryCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # Check for duplicate name
        db_repo = db.query(Repository).filter(Repository.name == repo.name).first()
        if db_repo:
            raise HTTPException(
                status_code=400, 
                detail="Repository with this name already exists"
            )
        
        # Check for duplicate path
        db_repo_path = db.query(Repository).filter(Repository.path == repo.path).first()
        if db_repo_path:
            raise HTTPException(
                status_code=400, 
                detail=f"Repository with path '{repo.path}' already exists with name '{db_repo_path.name}'"
            )
        
        db_repo = Repository(
            name=repo.name,
            path=repo.path
        )
        db_repo.set_passphrase(repo.passphrase)
        
        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)
        
        try:
            init_result = await borg_service.initialize_repository(db_repo)
            if not init_result["success"]:
                logger.warning(f"Repository '{repo.name}' created in database but Borg initialization failed: {init_result['message']}")
        except Exception as init_error:
            logger.error(f"Repository '{repo.name}' created in database but Borg initialization error: {init_error}")
        
        return db_repo
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create repository: {str(e)}"
        )


@router.get("/", response_model=List[RepositorySchema])
def list_repositories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    repositories = db.query(Repository).offset(skip).limit(limit).all()
    return repositories

@router.get("/scan")
async def scan_repositories():
    """Scan for existing repositories (alias for scan-existing for frontend compatibility)"""
    try:
        available_repos = await borg_service.scan_for_repositories()
        return {"repositories": available_repos}
    except Exception as e:
        logger.error(f"Error scanning for repositories: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan repositories: {str(e)}")


@router.get("/html", response_class=HTMLResponse)
def get_repositories_html(request: Request, db: Session = Depends(get_db)):
    """Get repositories as HTML for frontend display"""
    try:
        repositories = db.query(Repository).all()
        
        html_content = ""
        
        if not repositories:
            html_content = '''
                <div class="text-gray-500 text-center py-4">
                    <p>No repositories configured.</p>
                    <p class="text-sm mt-1">Create or import a repository to get started.</p>
                </div>
            '''
        else:
            html_content = '<div class="space-y-3">'
            
            for repo in repositories:
                html_content += f'''
                    <div class="border rounded-lg p-4 bg-white hover:bg-gray-50">
                        <div class="flex items-center justify-between">
                            <div class="flex-1">
                                <h4 class="font-medium text-gray-900">{repo.name}</h4>
                                <p class="text-sm text-gray-500">{repo.path}</p>
                                <p class="text-xs text-gray-400 mt-1">Created: {repo.created_at.strftime("%Y-%m-%d %H:%M") if repo.created_at else "Unknown"}</p>
                            </div>
                            <div class="flex space-x-2">
                                <button onclick="switchTab('archives'); document.getElementById('archive-repository-select').value = '{repo.id}'; loadArchives();" 
                                        class="px-3 py-1 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200">
                                    View Archives
                                </button>
                                <button onclick="borgitoryAppInstance.deleteRepository({repo.id}, '{repo.name}')" 
                                        class="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200">
                                    Delete
                                </button>
                            </div>
                        </div>
                    </div>
                '''
            
            html_content += '</div>'
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        error_html = f'''
            <div class="text-red-500 text-center py-4">
                <p>Error loading repositories: {str(e)}</p>
            </div>
        '''
        return HTMLResponse(content=error_html)


@router.get("/directories")
async def list_directories(path: str = "/repos"):
    """List directories at the given path for autocomplete functionality"""
    try:
        # Security: Only allow root directory or paths under /repos for safety
        if path != "/" and not path.startswith("/repos"):
            raise HTTPException(status_code=400, detail="Path must be root directory or under /repos directory")
        
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
                        ignored_dirs = {"opt", "home", "usr", "var", "bin", "sbin", "lib", "lib64", "etc", "proc", "sys", "dev", "run", "tmp", "boot", "mnt", "media", "srv", "root"}
                        
                        if item not in ignored_dirs:
                            directories.append({
                                "name": item,
                                "path": item_path
                            })
                    else:
                        directories.append({
                            "name": item,
                            "path": item_path
                        })
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {path}")
            return {"directories": []}
        
        # Sort directories alphabetically
        directories.sort(key=lambda x: x["name"].lower())
        
        return {"directories": directories}
        
    except Exception as e:
        logger.error(f"Error listing directories at {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list directories: {str(e)}")


@router.get("/{repo_id}", response_model=RepositorySchema)
def get_repository(repo_id: int, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.put("/{repo_id}", response_model=RepositorySchema)
def update_repository(repo_id: int, repo_update: RepositoryUpdate, db: Session = Depends(get_db)):
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


@router.delete("/{repo_id}")
async def delete_repository(repo_id: int, delete_borg_repo: bool = False, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    repo_name = repository.name
    
    # Check for active jobs before allowing deletion
    from app.models.database import Job, JobTask, Schedule
    active_jobs = db.query(Job).filter(
        Job.repository_id == repo_id,
        Job.status.in_(["running", "pending", "queued"])
    ).all()
    
    if active_jobs:
        active_job_types = [job.type for job in active_jobs]
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete repository '{repo_name}' - {len(active_jobs)} active job(s) running: {', '.join(active_job_types)}. Please wait for jobs to complete or cancel them first."
        )
    
    # Count entities that will be deleted for reporting
    jobs_count = db.query(Job).filter(Job.repository_id == repo_id).count()
    tasks_count = db.query(JobTask).join(Job).filter(Job.repository_id == repo_id).count()
    schedules_to_delete = db.query(Schedule).filter(Schedule.repository_id == repo_id).all()
    schedules_count = len(schedules_to_delete)
    
    # Remove scheduled jobs from APScheduler before deleting from database
    from app.services.scheduler_service import scheduler_service
    for schedule in schedules_to_delete:
        try:
            await scheduler_service.remove_schedule(schedule.id)
            logger.info(f"Removed scheduled job for schedule ID {schedule.id}")
        except Exception as e:
            logger.warning(f"Could not remove scheduled job for schedule ID {schedule.id}: {e}")
    
    # Delete the repository - this will cascade to jobs and schedules due to the 
    # cascade="all, delete-orphan" relationships defined in the Repository model.
    # Jobs will then cascade to JobTask records as well.
    db.delete(repository)
    db.commit()
    
    # TODO: If delete_borg_repo is True, we could also delete the actual Borg repository
    # This would require careful implementation to avoid data loss
    
    return {
        "message": f"Repository '{repo_name}' deleted successfully from database",
        "jobs_deleted": jobs_count,
        "tasks_deleted": tasks_count,
        "schedules_deleted": schedules_count,
        "note": "Actual Borg repository files were not deleted" if not delete_borg_repo else None
    }


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
        raise HTTPException(status_code=500, detail=f"Failed to list archives: {str(e)}")


@router.get("/{repo_id}/archives/html", response_class=HTMLResponse)
async def list_archives_html(repo_id: int, request: Request, db: Session = Depends(get_db)):
    """Get repository archives as HTML"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        try:
            archives = await borg_service.list_archives(repository)
            
            html_content = ""
            
            if not archives:
                html_content = '''
                    <div class="text-gray-500 text-center py-8">
                        <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                        </svg>
                        <h3 class="text-lg font-medium text-gray-900 mb-2">No Archives Found</h3>
                        <p class="text-sm">This repository doesn't contain any backup archives yet.</p>
                        <p class="text-sm mt-1">Create a backup to see archives here.</p>
                    </div>
                '''
            else:
                html_content = f'''
                    <div class="mb-4">
                        <div class="flex items-center justify-between">
                            <h3 class="text-lg font-medium text-gray-900">Archives for {repository.name}</h3>
                            <span class="text-sm text-gray-500">{len(archives)} archives</span>
                        </div>
                    </div>
                '''
                
                if len(archives) > 10:
                    html_content += '''
                        <div class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                            <p class="text-sm text-blue-700">
                                Showing the most recent 10 archives. Use the Borg command line to view older archives if needed.
                            </p>
                        </div>
                    '''
                
                html_content += '<div class="space-y-2">'
                
                # Show most recent archives first (limit to 10)
                recent_archives = archives[-10:] if len(archives) > 10 else archives
                recent_archives.reverse()  # Most recent first
                
                for archive in recent_archives:
                    # Parse archive information
                    archive_name = archive.get('name', 'Unknown')
                    archive_time = archive.get('time', '')
                    
                    # Format the timestamp if available
                    formatted_time = archive_time
                    if archive_time:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(archive_time.replace('Z', '+00:00'))
                            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            pass
                    
                    # Archive size information
                    size_info = ""
                    if 'stats' in archive:
                        stats = archive['stats']
                        if 'original_size' in stats:
                            # Convert bytes to human readable
                            size_bytes = stats['original_size']
                            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                                if size_bytes < 1024.0:
                                    size_info = f"{size_bytes:.1f} {unit}"
                                    break
                                size_bytes /= 1024.0
                    
                    html_content += f'''
                        <div class="border rounded-lg p-4 bg-white hover:bg-gray-50">
                            <div class="flex items-center justify-between">
                                <div class="flex-1">
                                    <div class="flex items-center space-x-3">
                                        <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                                        </svg>
                                        <div>
                                            <h4 class="font-medium text-gray-900">{archive_name}</h4>
                                            <div class="text-sm text-gray-500 space-x-4">
                                                <span>Created: {formatted_time}</span>
                                                {f'<span>Size: {size_info}</span>' if size_info else ''}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="flex-shrink-0">
                                    <button 
                                        onclick="viewArchiveContents('{repo_id}', '{archive_name}')"
                                        class="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 focus:ring-2 focus:ring-blue-500"
                                    >
                                        View Contents
                                    </button>
                                </div>
                            </div>
                        </div>
                    '''
                
                html_content += '</div>'
            
            return HTMLResponse(content=html_content)
            
        except Exception as e:
            logger.error(f"Error listing archives for repository {repo_id}: {e}")
            error_html = f'''
                <div class="text-red-500 text-center py-8">
                    <svg class="mx-auto h-12 w-12 text-red-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <h3 class="text-lg font-medium text-gray-900 mb-2">Error Loading Archives</h3>
                    <p class="text-sm text-red-600">{str(e)}</p>
                    <p class="text-sm text-gray-500 mt-2">Please check that the repository is accessible and try again.</p>
                </div>
            '''
            return HTMLResponse(content=error_html)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_archives_html: {e}")
        error_html = '''
            <div class="text-red-500 text-center py-8">
                <p>An unexpected error occurred while loading archives.</p>
            </div>
        '''
        return HTMLResponse(content=error_html)


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
    repo_id: int, 
    archive_name: str, 
    path: str = "",
    db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        contents = await borg_service.list_archive_directory_contents(
            repository, archive_name, path
        )
        return {
            "archive": archive_name,
            "path": path,
            "items": contents
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repo_id}/archives/{archive_name}/extract")
async def extract_file(
    repo_id: int,
    archive_name: str,
    file: str,
    db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        return await borg_service.extract_file_stream(repository, archive_name, file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=RepositorySchema, status_code=status.HTTP_201_CREATED)
async def import_repository(
    name: str = Form(...),
    path: str = Form(...),
    passphrase: str = Form(...),
    keyfile: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """Import an existing Borg repository"""
    try:
        # Check for duplicate name
        db_repo = db.query(Repository).filter(Repository.name == name).first()
        if db_repo:
            raise HTTPException(
                status_code=400, 
                detail="Repository with this name already exists"
            )
        
        # Check for duplicate path
        db_repo_path = db.query(Repository).filter(Repository.path == path).first()
        if db_repo_path:
            raise HTTPException(
                status_code=400, 
                detail=f"Repository with path '{path}' already exists with name '{db_repo_path.name}'"
            )
        
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
        db_repo = Repository(
            name=name,
            path=path
        )
        db_repo.set_passphrase(passphrase)
        
        # Store keyfile path if we have one (we'll add this field later)
        # For now, let's just proceed with verification
        
        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)
        
        # Verify we can access the repository with the given credentials
        # This tests the user-provided credentials, not the stored ones
        verification_successful = await borg_service.verify_repository_access(
            repo_path=path,
            passphrase=passphrase,
            keyfile_path=keyfile_path
        )
        
        if not verification_successful:
            # If verification fails, remove the database entry and keyfile
            if keyfile_path and os.path.exists(keyfile_path):
                os.remove(keyfile_path)
            db.delete(db_repo)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Failed to verify repository access. Please check the path, passphrase, and keyfile (if required)."
            )
        
        # If verification passed, get archive count for logging
        try:
            archives = await borg_service.list_archives(db_repo)
            logger.info(f"Successfully imported repository '{name}' with {len(archives)} archives")
        except Exception:
            logger.info(f"Successfully imported repository '{name}' (could not count archives)")
        
        return db_repo
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import repository: {str(e)}"
        )