"""Add database constraints and performance indexes

Revision ID: 3e16f40409fc
Revises: 9ed408182d00
Create Date: 2025-09-05 12:10:12.010468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e16f40409fc'
down_revision: Union[str, Sequence[str], None] = '9ed408182d00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add database constraints and performance indexes."""
    
    # === PERFORMANCE INDEXES ===
    
    # 1. Job Status + Repository queries (most common query pattern)
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index('ix_jobs_status_repository', ['status', 'repository_id'])
        batch_op.create_index('ix_jobs_repository_started', ['repository_id', 'started_at'])
        batch_op.create_index('ix_jobs_status_started', ['status', 'started_at'])
        batch_op.create_index('ix_jobs_finished_at', ['finished_at'])
        
    # 2. Schedule queries for the scheduler
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.create_index('ix_schedules_enabled_next_run', ['enabled', 'next_run'])
        batch_op.create_index('ix_schedules_repository_enabled', ['repository_id', 'enabled'])
        
    # 3. Job Task execution order
    with op.batch_alter_table('job_tasks', schema=None) as batch_op:
        batch_op.create_index('ix_job_tasks_job_order', ['job_id', 'task_order'])
        batch_op.create_index('ix_job_tasks_status', ['status'])
        
    # 4. User session cleanup and lookups
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index('ix_user_sessions_expires_at', ['expires_at'])
        batch_op.create_index('ix_user_sessions_user_active', ['user_id', 'last_activity'])
        
    # 5. Configuration lookups by enabled status
    with op.batch_alter_table('cleanup_configs', schema=None) as batch_op:
        batch_op.create_index('ix_cleanup_configs_enabled', ['enabled'])
        
    with op.batch_alter_table('cloud_sync_configs', schema=None) as batch_op:
        batch_op.create_index('ix_cloud_sync_configs_enabled', ['enabled'])
        batch_op.create_index('ix_cloud_sync_configs_provider', ['provider'])
        
    with op.batch_alter_table('notification_configs', schema=None) as batch_op:
        batch_op.create_index('ix_notification_configs_enabled', ['enabled'])
        batch_op.create_index('ix_notification_configs_provider', ['provider'])
        
    with op.batch_alter_table('repository_check_configs', schema=None) as batch_op:
        batch_op.create_index('ix_repository_check_configs_enabled', ['enabled'])
        
    # === CHECK CONSTRAINTS ===
    
    # Job status validation
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_jobs_status_valid',
            sa.text("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')")
        )
        batch_op.create_check_constraint(
            'ck_jobs_type_valid', 
            sa.text("type IN ('backup', 'restore', 'list', 'check', 'prune', 'sync', 'composite')")
        )
        batch_op.create_check_constraint(
            'ck_jobs_job_type_valid',
            sa.text("job_type IN ('simple', 'composite')")
        )
        # Ensure finished_at is after started_at when both are set
        batch_op.create_check_constraint(
            'ck_jobs_finish_after_start',
            sa.text("finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at")
        )
        # Ensure total_tasks >= completed_tasks
        batch_op.create_check_constraint(
            'ck_jobs_completed_tasks_valid',
            sa.text("completed_tasks >= 0 AND completed_tasks <= total_tasks")
        )
        
    # Job task status validation  
    with op.batch_alter_table('job_tasks', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_job_tasks_status_valid',
            sa.text("status IN ('pending', 'running', 'completed', 'failed', 'skipped')")
        )
        # Ensure task_order is positive
        batch_op.create_check_constraint(
            'ck_job_tasks_order_positive',
            sa.text("task_order > 0")
        )
        # Ensure completed_at is after started_at when both are set
        batch_op.create_check_constraint(
            'ck_job_tasks_completion_time',
            sa.text("completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at")
        )
        
    # Cloud sync provider validation
    with op.batch_alter_table('cloud_sync_configs', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_cloud_sync_provider_valid',
            sa.text("provider IN ('s3', 'sftp', 'azure', 'gcp')")
        )
        # SFTP port validation
        batch_op.create_check_constraint(
            'ck_cloud_sync_port_valid',
            sa.text("port IS NULL OR (port > 0 AND port <= 65535)")
        )
        
    # Repository check type validation
    with op.batch_alter_table('repository_check_configs', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_check_type_valid',
            sa.text("check_type IN ('full', 'repository_only', 'archives_only')")
        )
        # Max duration should be positive if set
        batch_op.create_check_constraint(
            'ck_max_duration_positive',
            sa.text("max_duration IS NULL OR max_duration > 0")
        )
        
    # Cleanup strategy validation
    with op.batch_alter_table('cleanup_configs', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_cleanup_strategy_valid',
            sa.text("strategy IN ('simple', 'advanced')")
        )
        # Ensure positive retention values
        batch_op.create_check_constraint(
            'ck_cleanup_retention_positive',
            sa.text("""
                (keep_within_days IS NULL OR keep_within_days > 0) AND
                (keep_daily IS NULL OR keep_daily >= 0) AND
                (keep_weekly IS NULL OR keep_weekly >= 0) AND
                (keep_monthly IS NULL OR keep_monthly >= 0) AND
                (keep_yearly IS NULL OR keep_yearly >= 0)
            """)
        )
        
    # Notification provider validation
    with op.batch_alter_table('notification_configs', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_notification_provider_valid',
            sa.text("provider IN ('pushover', 'email', 'webhook')")
        )
        
    # User session expiration validation
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_session_expiry_future',
            sa.text("expires_at > created_at")
        )
        # Last activity should not be before creation
        batch_op.create_check_constraint(
            'ck_session_activity_valid',
            sa.text("last_activity >= created_at")
        )
        
    # === UNIQUE CONSTRAINTS ===
    
    # Ensure unique task order within each job
    with op.batch_alter_table('job_tasks', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_job_tasks_job_order', ['job_id', 'task_order'])
        
    # Ensure unique schedule names per repository  
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_schedules_repo_name', ['repository_id', 'name'])


def downgrade() -> None:
    """Remove database constraints and performance indexes."""
    
    # Remove unique constraints
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.drop_constraint('uq_schedules_repo_name', type_='unique')
        
    with op.batch_alter_table('job_tasks', schema=None) as batch_op:
        batch_op.drop_constraint('uq_job_tasks_job_order', type_='unique')
    
    # Remove check constraints
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('ck_session_activity_valid', type_='check')
        batch_op.drop_constraint('ck_session_expiry_future', type_='check')
        
    with op.batch_alter_table('notification_configs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_provider_valid', type_='check')
        
    with op.batch_alter_table('cleanup_configs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cleanup_retention_positive', type_='check')
        batch_op.drop_constraint('ck_cleanup_strategy_valid', type_='check')
        
    with op.batch_alter_table('repository_check_configs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_max_duration_positive', type_='check')
        batch_op.drop_constraint('ck_check_type_valid', type_='check')
        
    with op.batch_alter_table('cloud_sync_configs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cloud_sync_port_valid', type_='check')
        batch_op.drop_constraint('ck_cloud_sync_provider_valid', type_='check')
        
    with op.batch_alter_table('job_tasks', schema=None) as batch_op:
        batch_op.drop_constraint('ck_job_tasks_completion_time', type_='check')
        batch_op.drop_constraint('ck_job_tasks_order_positive', type_='check')
        batch_op.drop_constraint('ck_job_tasks_status_valid', type_='check')
        
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_jobs_completed_tasks_valid', type_='check')
        batch_op.drop_constraint('ck_jobs_finish_after_start', type_='check')
        batch_op.drop_constraint('ck_jobs_job_type_valid', type_='check')
        batch_op.drop_constraint('ck_jobs_type_valid', type_='check')
        batch_op.drop_constraint('ck_jobs_status_valid', type_='check')
    
    # Remove indexes
    with op.batch_alter_table('repository_check_configs', schema=None) as batch_op:
        batch_op.drop_index('ix_repository_check_configs_enabled')
        
    with op.batch_alter_table('notification_configs', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_configs_provider')
        batch_op.drop_index('ix_notification_configs_enabled')
        
    with op.batch_alter_table('cloud_sync_configs', schema=None) as batch_op:
        batch_op.drop_index('ix_cloud_sync_configs_provider')
        batch_op.drop_index('ix_cloud_sync_configs_enabled')
        
    with op.batch_alter_table('cleanup_configs', schema=None) as batch_op:
        batch_op.drop_index('ix_cleanup_configs_enabled')
        
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_user_sessions_user_active')
        batch_op.drop_index('ix_user_sessions_expires_at')
        
    with op.batch_alter_table('job_tasks', schema=None) as batch_op:
        batch_op.drop_index('ix_job_tasks_status')
        batch_op.drop_index('ix_job_tasks_job_order')
        
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.drop_index('ix_schedules_repository_enabled')
        batch_op.drop_index('ix_schedules_enabled_next_run')
        
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_finished_at')
        batch_op.drop_index('ix_jobs_status_started')
        batch_op.drop_index('ix_jobs_repository_started')
        batch_op.drop_index('ix_jobs_status_repository')
