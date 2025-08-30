from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.models.database import Repository, Job, get_db
from app.services.rclone_service import rclone_service

router = APIRouter()


class S3RemoteConfig(BaseModel):
    remote_name: str
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"
    endpoint: str = None


class SyncRequest(BaseModel):
    repository_id: int
    remote_name: str
    bucket_name: str
    path_prefix: str = ""


@router.post("/remotes/s3")
async def configure_s3_remote(config: S3RemoteConfig):
    """Configure a new S3 remote"""
    success = await rclone_service.configure_s3_remote(
        remote_name=config.remote_name,
        access_key_id=config.access_key_id,
        secret_access_key=config.secret_access_key,
        region=config.region,
        endpoint=config.endpoint
    )
    
    if success:
        return {"message": f"S3 remote '{config.remote_name}' configured successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to configure S3 remote")


@router.get("/remotes")
def list_remotes():
    """List all configured Rclone remotes"""
    remotes = rclone_service.get_configured_remotes()
    return {"remotes": remotes}


@router.post("/remotes/{remote_name}/test")
async def test_remote_connection(remote_name: str, bucket_name: str):
    """Test connection to an S3 remote"""
    result = await rclone_service.test_s3_connection(remote_name, bucket_name)
    
    if result["status"] == "success":
        return result
    else:
        raise HTTPException(status_code=400, detail=result["message"])


async def sync_repository_task(
    repository_id: int,
    remote_name: str,
    bucket_name: str,
    path_prefix: str,
    job_id: int
):
    """Background task to sync repository to S3"""
    from app.models.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Get fresh instances from the new session
        job = db.query(Job).filter(Job.id == job_id).first()
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        
        if not job or not repository:
            return
        
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
        
        log_output = []
        async for progress in rclone_service.sync_repository_to_s3(
            repository=repository,
            remote_name=remote_name,
            bucket_name=bucket_name,
            path_prefix=path_prefix
        ):
            if progress.get("type") == "log":
                log_output.append(f"[{progress['stream']}] {progress['message']}")
            elif progress.get("type") == "error":
                job.status = "failed"
                job.error = progress["message"]
                job.finished_at = datetime.utcnow()
                job.log_output = "\n".join(log_output)
                db.commit()
                return
            elif progress.get("type") == "completed":
                job.status = "completed" if progress["status"] == "success" else "failed"
                job.finished_at = datetime.utcnow()
                job.log_output = "\n".join(log_output)
                db.commit()
                return
        
        job.status = "completed"
        job.finished_at = datetime.utcnow()
        job.log_output = "\n".join(log_output)
        db.commit()
        
    except Exception as e:
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error = str(e)
                job.finished_at = datetime.utcnow()
                db.commit()
        except:
            pass
    finally:
        db.close()




@router.post("/sync")
async def sync_repository(
    sync_request: SyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync a repository to S3"""
    repository = db.query(Repository).filter(
        Repository.id == sync_request.repository_id
    ).first()
    
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Create job record
    job = Job(
        repository_id=repository.id,
        type="sync",
        status="pending"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Start background sync task
    background_tasks.add_task(
        sync_repository_task,
        repository.id,
        sync_request.remote_name,
        sync_request.bucket_name,
        sync_request.path_prefix,
        job.id
    )
    
    return {"job_id": job.id, "status": "started"}