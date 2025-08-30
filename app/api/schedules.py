from typing import List, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
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
        scheduler_service.add_schedule(db_schedule.id, db_schedule.name, db_schedule.cron_expression)
    except Exception as e:
        # Rollback database changes if scheduler fails
        db.delete(db_schedule)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to schedule job: {str(e)}")
    
    return db_schedule


@router.get("/html", response_class=HTMLResponse)
def get_schedules_html(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get schedules as formatted HTML"""
    schedules = db.query(Schedule).offset(skip).limit(limit).all()
    
    if not schedules:
        return '<div class="text-gray-500 text-sm">No schedules configured</div>'
    
    html_items = []
    for schedule in schedules:
        status_class = 'bg-green-100 text-green-700' if schedule.enabled else 'bg-gray-100 text-gray-700'
        status_text = 'Active' if schedule.enabled else 'Disabled'
        row_class = '' if schedule.enabled else 'bg-gray-50'
        text_class = '' if schedule.enabled else 'text-gray-500'
        
        last_run = schedule.last_run.strftime('%m/%d/%Y, %I:%M:%S %p') if schedule.last_run else 'Never run'
        next_run = schedule.next_run.strftime('%m/%d/%Y, %I:%M:%S %p') if schedule.next_run else ''
        
        toggle_class = 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200' if schedule.enabled else 'bg-green-100 text-green-700 hover:bg-green-200'
        toggle_text = 'Disable' if schedule.enabled else 'Enable'
        
        html_items.append(f'''
            <div class="flex items-center justify-between p-3 border rounded-lg mb-2 {row_class}">
                <div>
                    <div class="font-medium {text_class}">{schedule.name}</div>
                    <div class="text-sm text-gray-500">
                        <span class="inline-flex px-2 py-1 text-xs rounded-full {status_class}">
                            {status_text}
                        </span>
                        Last: {last_run}
                        {' | Next: ' + next_run if next_run else ''}
                    </div>
                    <div class="text-xs text-gray-400">{schedule.cron_expression}</div>
                </div>
                <div class="flex space-x-2">
                    <button onclick="toggleSchedule({schedule.id})" 
                            class="px-3 py-1 text-sm {toggle_class} rounded">
                        {toggle_text}
                    </button>
                    <button onclick="deleteSchedule({schedule.id}, '{schedule.name}')" 
                            class="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200">
                        Delete
                    </button>
                </div>
            </div>
        ''')
    
    return ''.join(html_items)


@router.get("/upcoming/html", response_class=HTMLResponse)
def get_upcoming_backups_html():
    """Get upcoming scheduled backups as formatted HTML"""
    try:
        jobs = scheduler_service.get_scheduled_jobs()
        
        if not jobs:
            return '<div class="text-gray-500 text-sm">No upcoming scheduled backups</div>'
        
        html_items = []
        for job in jobs:
            try:
                # Handle different datetime formats from APScheduler
                next_run_raw = job.get('next_run')
                if not next_run_raw:
                    continue
                
                # Convert to datetime object if it's not already
                if isinstance(next_run_raw, str):
                    # Try different datetime formats
                    try:
                        next_run = datetime.fromisoformat(next_run_raw.replace('Z', '+00:00'))
                    except:
                        try:
                            next_run = datetime.fromisoformat(next_run_raw)
                        except:
                            # Skip if we can't parse the datetime
                            continue
                else:
                    # Assume it's already a datetime object
                    next_run = next_run_raw
                
                # Calculate time difference
                now = datetime.now()
                if next_run.tzinfo:
                    # If next_run is timezone aware, make now timezone aware too
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                
                time_diff_seconds = (next_run - now).total_seconds()
                time_diff_ms = int(time_diff_seconds * 1000)
                time_until = format_time_until(time_diff_ms)
                
                # Format cron description
                cron_description = format_cron_trigger(job.get('trigger', ''))
                
                # Format the datetime for display
                next_run_display = next_run.strftime('%m/%d/%Y, %I:%M:%S %p')
                
                html_items.append(f'''
                    <div class="flex items-center justify-between p-4 border rounded-lg mb-3">
                        <div>
                            <div class="font-medium text-gray-900">{job.get('name', 'Unknown')}</div>
                            <div class="text-sm text-gray-600">
                                <span class="font-medium">Next run:</span> {next_run_display}
                            </div>
                            <div class="text-sm text-gray-500">
                                <span class="font-medium">Time until:</span> {time_until}
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-sm text-gray-500 font-medium">{cron_description}</div>
                        </div>
                    </div>
                ''')
                
            except Exception as job_error:
                # Skip individual jobs that fail to process
                print(f"Error processing job {job.get('name', 'Unknown')}: {job_error}")
                continue
        
        return ''.join(html_items) if html_items else '<div class="text-gray-500 text-sm">No upcoming scheduled backups</div>'
        
    except Exception as e:
        return f'<div class="text-red-500 text-sm">Error loading upcoming backups: {str(e)}</div>'


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
        scheduler_service.update_schedule(schedule.id, schedule.name, schedule.cron_expression, schedule.enabled)
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


def format_cron_trigger(trigger_str: str) -> str:
    """Convert cron trigger to human readable format"""
    try:
        import re
        cron_match = re.search(r'cron\[([^\]]+)\]', trigger_str)
        if not cron_match:
            return trigger_str
        
        cron_parts = {}
        parts = cron_match.group(1).split(', ')
        
        for part in parts:
            key, value = part.split('=', 1)
            cron_parts[key] = value.strip("'")
        
        minute = cron_parts.get('minute', '*')
        hour = cron_parts.get('hour', '*')
        day = cron_parts.get('day', '*')
        month = cron_parts.get('month', '*')
        day_of_week = cron_parts.get('day_of_week', '*')
        
        # Convert to human readable format
        if minute == '0' and hour != '*' and day == '*' and month == '*' and day_of_week == '*':
            return f"Daily at {format_hour(hour)}"
        elif minute == '0' and hour != '*' and day == '*' and month == '*' and day_of_week != '*':
            day_name = get_day_name(day_of_week)
            return f"Weekly on {day_name} at {format_hour(hour)}"
        elif minute == '0' and hour != '*' and day != '*' and month == '*' and day_of_week == '*':
            if ',' in day:
                return f"Twice monthly ({day}) at {format_hour(hour)}"
            elif '/' in day:
                return f"Every {day.split('/')[1]} days at {format_hour(hour)}"
            else:
                return f"Monthly on {day} at {format_hour(hour)}"
        elif minute == '0' and hour != '*' and '-' in day and day_of_week != '*':
            day_name = get_day_name(day_of_week)
            return f"Third {day_name} of month at {format_hour(hour)}"
        else:
            return f"{minute} {hour} {day} {month} {day_of_week}"
    except:
        return trigger_str


def format_hour(hour_str: str) -> str:
    """Convert 24-hour to 12-hour format"""
    try:
        h = int(hour_str)
        if h == 0:
            return "12:00 AM"
        elif h < 12:
            return f"{h}:00 AM"
        elif h == 12:
            return "12:00 PM"
        else:
            return f"{h - 12}:00 PM"
    except:
        return hour_str


def get_day_name(day_of_week: str) -> str:
    """Convert day number to day name"""
    days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    try:
        return days[int(day_of_week)]
    except:
        return 'Unknown'


def format_time_until(milliseconds: int) -> str:
    """Format time until next run"""
    if milliseconds < 0:
        return 'Overdue'
    
    seconds = milliseconds // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    
    if days > 0:
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours}h"
    elif hours > 0:
        remaining_minutes = minutes % 60
        return f"{hours}h {remaining_minutes}m"
    elif minutes > 0:
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{seconds}s"