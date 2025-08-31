import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile, Request
from sqlalchemy.orm import Session

from app.models.database import Repository, User, get_db
from app.models.schemas import Repository as RepositorySchema, RepositoryCreate, RepositoryUpdate
from app.services.borg_service import borg_service
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=RepositorySchema, status_code=status.HTTP_201_CREATED)
async def create_repository(
    repo: RepositoryCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        db_repo = db.query(Repository).filter(Repository.name == repo.name).first()
        if db_repo:
            raise HTTPException(
                status_code=400, 
                detail="Repository with this name already exists"
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


@router.get("/html")
def list_repositories_html(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Return HTML-rendered repository list for HTMX"""
    from fastapi.responses import HTMLResponse
    
    repositories = db.query(Repository).offset(skip).limit(limit).all()
    
    if not repositories:
        return HTMLResponse('<div class="text-gray-500 p-4">No repositories configured</div>')
    
    html_items = []
    for repo in repositories:
        created_date = repo.created_at.strftime('%Y-%m-%d') if repo.created_at else 'Unknown'
        html_items.append(f'''
            <div class="flex items-center justify-between p-3 border rounded-lg mb-2">
                <div>
                    <div class="font-medium">{repo.name}</div>
                    <div class="text-sm text-gray-500">{repo.path}</div>
                    <div class="text-xs text-gray-400">Created: {created_date}</div>
                </div>
                <div class="flex space-x-2">
                    <button onclick="borgitoryAppInstance.selectRepository({repo.id})" 
                            class="px-3 py-1 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200">
                        View Archives
                    </button>
                    <button onclick="borgitoryAppInstance.deleteRepository({repo.id}, '{repo.name}')" 
                            class="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200">
                        Delete
                    </button>
                </div>
            </div>
        ''')
    
    return HTMLResponse(''.join(html_items))


@router.post("/scan-existing/start")
async def start_repository_scan():
    """Start scanning for existing Borg repositories in the repos directory"""
    try:
        job_id = await borg_service.start_repository_scan("/repos")
        return {"job_id": job_id, "status": "started"}
    except Exception as e:
        logger.error(f"Error starting repository scan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")

@router.get("/scan-existing/status/{job_id}")
async def check_scan_status(job_id: str):
    """Check status of repository scan job"""
    try:
        status = await borg_service.check_scan_status(job_id)
        return status
    except Exception as e:
        logger.error(f"Error checking scan status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check status: {str(e)}")

@router.get("/scan-existing/results/{job_id}")
async def get_scan_results(job_id: str, db: Session = Depends(get_db)):
    """Get results of completed repository scan"""
    try:
        repositories = await borg_service.get_scan_results(job_id)
        
        # Filter out already imported repositories
        imported_repos = db.query(Repository).all()
        imported_paths = {repo.path for repo in imported_repos}
        
        available_repos = [repo for repo in repositories if repo["path"] not in imported_paths]
        
        return {"repositories": available_repos}
    except Exception as e:
        logger.error(f"Error getting scan results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")

@router.get("/scan-existing")
async def scan_existing_repositories(db: Session = Depends(get_db)):
    """Legacy endpoint - use the new start/status/results endpoints instead"""
    try:
        imported_repos = db.query(Repository).all()
        imported_paths = {repo.path for repo in imported_repos}
        
        repositories = await borg_service.scan_for_repositories("/repos")
        
        available_repos = [repo for repo in repositories if repo["path"] not in imported_paths]
        
        return {"repositories": available_repos}
    except Exception as e:
        logger.error(f"Error scanning for repositories: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan repositories: {str(e)}")


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
def delete_repository(repo_id: int, delete_borg_repo: bool = False, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    repo_name = repository.name
    
    from app.models.database import Job
    jobs_deleted = db.query(Job).filter(Job.repository_id == repo_id).delete()
    
    from app.models.database import Schedule
    schedules_deleted = db.query(Schedule).filter(Schedule.repository_id == repo_id).delete()
    
    db.delete(repository)
    db.commit()
    
    # TODO: If delete_borg_repo is True, we could also delete the actual Borg repository
    # This would require careful implementation to avoid data loss
    
    return {
        "message": f"Repository '{repo_name}' deleted successfully from database",
        "jobs_deleted": jobs_deleted,
        "schedules_deleted": schedules_deleted,
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
async def get_archive_contents(repo_id: int, archive_name: str, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        contents = await borg_service.list_archive_contents(repository, archive_name)
        return {"archive": archive_name, "contents": contents}
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
        db_repo = db.query(Repository).filter(Repository.name == name).first()
        if db_repo:
            raise HTTPException(
                status_code=400, 
                detail="Repository with this name already exists"
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
                detail=f"Failed to verify repository access. Please check the path, passphrase, and keyfile (if required)."
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