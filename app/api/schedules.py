from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import Schedule, Repository, get_db
from app.models.schemas import Schedule as ScheduleSchema, ScheduleCreate
from app.services.scheduler_service import scheduler_service

router = APIRouter()


@router.post("/", response_model=ScheduleSchema, status_code=status.HTTP_201_CREATED)
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):
    repository = db.query(Repository).filter(Repository.id == schedule.repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(schedule.cron_expression)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {str(e)}")
    
    db_schedule = Schedule(
        name=schedule.name,
        repository_id=schedule.repository_id,
        cron_expression=schedule.cron_expression,
        enabled=True
    )
    
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    
    # Add to scheduler
    try:
        scheduler_service.add_schedule(db_schedule)
    except Exception as e:
        # Rollback database changes if scheduler fails
        db.delete(db_schedule)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to schedule job: {str(e)}")
    
    return db_schedule


@router.get("/", response_model=List[ScheduleSchema])
def list_schedules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    schedules = db.query(Schedule).offset(skip).limit(limit).all()
    return schedules


@router.get("/{schedule_id}", response_model=ScheduleSchema)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.put("/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    schedule.enabled = not schedule.enabled
    db.commit()
    
    # Update scheduler
    try:
        scheduler_service.update_schedule(schedule)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update schedule: {str(e)}")
    
    return {"message": f"Schedule {'enabled' if schedule.enabled else 'disabled'}"}


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Remove from scheduler
    scheduler_service.remove_schedule(schedule_id)
    
    # Delete from database
    db.delete(schedule)
    db.commit()
    
    return {"message": "Schedule deleted successfully"}


@router.get("/jobs/active")
def get_active_scheduled_jobs():
    """Get all active scheduled jobs"""
    return {"jobs": scheduler_service.get_scheduled_jobs()}