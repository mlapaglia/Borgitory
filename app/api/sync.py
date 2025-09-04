import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.database import Repository, Job, get_db
from app.services.rclone_service import rclone_service, RcloneService

logger = logging.getLogger(__name__)

router = APIRouter()


class S3RemoteConfig(BaseModel):
    remote_name: str
    access_key_id: str
    secret_access_key: str


class SyncRequest(BaseModel):
    repository_id: int
    remote_name: str
    bucket_name: str
    path_prefix: str = ""


@router.post("/remotes/s3")
async def configure_s3_remote(
    config: S3RemoteConfig, rclone: RcloneService = Depends(lambda: rclone_service)
):
    """Configure a new S3 remote"""
    success = await rclone.configure_s3_remote(
        remote_name=config.remote_name,
        access_key_id=config.access_key_id,
        secret_access_key=config.secret_access_key,
    )

    if success:
        return {"message": f"S3 remote '{config.remote_name}' configured successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to configure S3 remote")


@router.get("/remotes")
def list_remotes(rclone: RcloneService = Depends(lambda: rclone_service)):
    """List all configured Rclone remotes"""
    remotes = rclone.get_configured_remotes()
    return {"remotes": remotes}


@router.post("/remotes/{remote_name}/test")
async def test_remote_connection(
    remote_name: str,
    bucket_name: str,
    rclone: RcloneService = Depends(lambda: rclone_service),
):
    """Test connection to an S3 remote"""
    result = await rclone.test_s3_connection(remote_name, bucket_name)

    if result["status"] == "success":
        return result
    else:
        raise HTTPException(status_code=400, detail=result["message"])


async def sync_repository_task(
    repository_id: int,
    config_name: str,
    bucket_name: str,
    path_prefix: str,
    job_id: int,
    db_session: Session = None,
    rclone: RcloneService = None,
):
    """Background task to sync repository to S3"""
    logger.info("sync_repository_task STARTED")
    logger.info("Parameters:")
    logger.info(f"  - repository_id: {repository_id}")
    logger.info(f"  - config_name: {config_name}")
    logger.info(f"  - bucket_name: {bucket_name}")
    logger.info(f"  - path_prefix: {path_prefix}")
    logger.info(f"  - job_id: {job_id}")

    # Use provided session or create new one (for testing vs production)
    if db_session is None:
        from app.models.database import SessionLocal

        db = SessionLocal()
        should_close_db = True
    else:
        db = db_session
        should_close_db = False

    # Use provided rclone service or default (for testing vs production)
    if rclone is None:
        rclone = rclone_service

    try:
        # Get fresh instances from the new session
        logger.info("Looking up database records...")
        job = db.query(Job).filter(Job.id == job_id).first()
        repository = db.query(Repository).filter(Repository.id == repository_id).first()

        # Get the cloud backup config
        from app.models.database import CloudSyncConfig

        config = (
            db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.name == config_name)
            .first()
        )

        logger.info("Database lookup results:")
        logger.info(f"  - job: {'Found' if job else 'NOT FOUND'}")
        logger.info(f"  - repository: {'Found' if repository else 'NOT FOUND'}")
        logger.info(f"  - config: {'Found' if config else 'NOT FOUND'}")

        if not job or not repository or not config:
            logger.error("Missing required database records - aborting sync task")
            return

        # Get credentials
        logger.info(f"Getting credentials for config '{config.name}'...")
        access_key, secret_key = config.get_credentials()
        logger.info(
            f"Got credentials (access_key: {'***' + access_key[-4:] if access_key else 'None'})"
        )

        logger.info(f"Updating job {job_id} status to running...")
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
        logger.info("Job status updated")

        logger.info(f"Starting rclone sync to {bucket_name}...")
        log_output = []
        async for progress in rclone.sync_repository_to_s3(
            repository=repository,
            access_key_id=access_key,
            secret_access_key=secret_key,
            bucket_name=bucket_name,
            path_prefix=path_prefix,
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
                job.status = (
                    "completed" if progress["status"] == "success" else "failed"
                )
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
        except Exception:
            pass
    finally:
        if should_close_db:
            db.close()


@router.post("/sync")
async def sync_repository(
    sync_request: SyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    rclone: RcloneService = Depends(lambda: rclone_service),
):
    """Sync a repository to S3"""
    repository = (
        db.query(Repository).filter(Repository.id == sync_request.repository_id).first()
    )

    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Create job record
    job = Job(repository_id=repository.id, type="sync", status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    # Start background sync task
    background_tasks.add_task(
        sync_repository_task,
        repository.id,
        sync_request.remote_name,  # This is now config name, not remote name
        sync_request.bucket_name,
        sync_request.path_prefix,
        job.id,
        None,  # db_session - let task create its own
        rclone,  # pass the injected rclone service
    )

    return {"job_id": job.id, "status": "started"}
