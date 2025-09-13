"""
Clean FastAPI dependencies following 2024 best practices.

This demonstrates proper dependency injection without caching or global state,
making testing with app.dependency_overrides work perfectly.
"""

from typing import Annotated, Callable
from fastapi import Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from app.models.repository import create_database_engine, create_session_factory
from app.services.interfaces import (
    SecurityValidator,
    CommandExecutor,
    BorgVerificationService, 
    RepositoryDataService,
    RepositoryImportService,
    FileSystemService
)
from app.services.implementations import (
    SimpleSecurityValidator,
    SimpleCommandExecutor,
    SimpleBorgVerificationService,
    SimpleRepositoryDataService,
    RepositoryImportServiceImpl,
    SimpleFileSystemService
)
from app.services.repository_service import (
    SqlAlchemyRepositoryDataService,
    RepositoryManagementService
)
from app.services.repository_query_service import RepositoryQueryService
from app.services.job_service import (
    JobExecutionService,
    JobManagementService
)
from app.services.notification_service import NotificationServiceImpl
from app.services.workflow_service import (
    TaskExecutionServiceImpl,
    JobWorkflowServiceImpl
)

# SQLAlchemy 2.0 database setup following tutorial best practices
# Using factory functions instead of global state for better DI and testing

def get_templates() -> Jinja2Templates:
    """Get Jinja2 templates instance for rendering HTML responses."""
    return Jinja2Templates(directory="templates")


def get_engine():
    """Get database engine instance."""
    return create_database_engine(echo=True)  # Enable SQL logging for development


def get_session_factory(engine=Depends(get_engine)) -> sessionmaker:
    """Get session factory using dependency injection."""
    return create_session_factory(engine)


# Database dependency following SQLAlchemy 2.0 + FastAPI best practices
def get_db(session_factory: sessionmaker = Depends(get_session_factory)):
    """
    Database session dependency following SQLAlchemy 2.0 tutorial.
    
    Uses proper session lifecycle with automatic commit/rollback.
    """
    with session_factory() as session:
        try:
            yield session
            session.commit()  # Auto-commit on success
        except Exception:
            session.rollback()  # Auto-rollback on error
            raise


# Service dependencies (following FastAPI official pattern)
def get_security_validator() -> SecurityValidator:
    """Get security validator instance."""
    return SimpleSecurityValidator()


def get_command_executor() -> CommandExecutor:
    """Get command executor instance."""
    return SimpleCommandExecutor()


def get_filesystem_service() -> FileSystemService:
    """Get filesystem service instance."""
    return SimpleFileSystemService()


def get_borg_verification_service(
    command_executor: Annotated[CommandExecutor, Depends(get_command_executor)]
) -> BorgVerificationService:
    """Get Borg verification service with dependency injection."""
    return SimpleBorgVerificationService(command_executor)


def get_repository_data_service() -> RepositoryDataService:
    """Get repository data service instance using real SQLAlchemy."""
    return SqlAlchemyRepositoryDataService()


def get_repository_management_service(
    security_validator: Annotated[SecurityValidator, Depends(get_security_validator)],
    data_service: Annotated[RepositoryDataService, Depends(get_repository_data_service)]
) -> RepositoryManagementService:
    """Get repository management service with clean FastAPI DI."""
    return RepositoryManagementService(security_validator, data_service)


def get_repository_import_service(
    security_validator: Annotated[SecurityValidator, Depends(get_security_validator)],
    borg_service: Annotated[BorgVerificationService, Depends(get_borg_verification_service)],
    data_service: Annotated[RepositoryDataService, Depends(get_repository_data_service)]
) -> RepositoryImportService:
    """
    Get repository import service with clean dependency injection.
    
    This demonstrates proper FastAPI dependency chaining following 2024 best practices.
    """
    return RepositoryImportServiceImpl(security_validator, borg_service, data_service)


def get_repository_query_service(
    command_executor: Annotated[CommandExecutor, Depends(get_command_executor)],
    security_validator: Annotated[SecurityValidator, Depends(get_security_validator)],
    filesystem_service: Annotated[FileSystemService, Depends(get_filesystem_service)]
) -> RepositoryQueryService:
    """
    Get repository query service for synchronous operations.
    
    Handles immediate operations like scanning, validation, directory listing.
    """
    return RepositoryQueryService(command_executor, security_validator, filesystem_service)


def get_session_factory_for_tasks(session_factory: sessionmaker = Depends(get_session_factory)) -> sessionmaker:
    """Get session factory for background tasks."""
    return session_factory


def get_job_execution_service(
    command_executor: Annotated[CommandExecutor, Depends(get_command_executor)],
    security_validator: Annotated[SecurityValidator, Depends(get_security_validator)],
    session_factory: sessionmaker = Depends(get_session_factory_for_tasks)
) -> JobExecutionService:
    """Get job execution service with clean FastAPI DI."""
    return JobExecutionService(command_executor, security_validator, session_factory)


def get_job_management_service(
    job_executor: Annotated[JobExecutionService, Depends(get_job_execution_service)]
) -> JobManagementService:
    """Get job management service with clean FastAPI DI."""
    return JobManagementService(job_executor)


def get_notification_service() -> NotificationServiceImpl:
    """Get notification service instance."""
    return NotificationServiceImpl()


def get_task_execution_service(
    command_executor: Annotated[CommandExecutor, Depends(get_command_executor)],
    notification_service: Annotated[NotificationServiceImpl, Depends(get_notification_service)],
    job_executor: Annotated[JobExecutionService, Depends(get_job_execution_service)],
    session_factory: sessionmaker = Depends(get_session_factory_for_tasks)
) -> TaskExecutionServiceImpl:
    """Get task execution service with clean FastAPI DI."""
    return TaskExecutionServiceImpl(command_executor, notification_service, job_executor, session_factory)


def get_workflow_service(
    task_executor: Annotated[TaskExecutionServiceImpl, Depends(get_task_execution_service)],
    session_factory: sessionmaker = Depends(get_session_factory_for_tasks)
) -> JobWorkflowServiceImpl:
    """Get workflow service with clean FastAPI DI."""
    return JobWorkflowServiceImpl(task_executor, session_factory)


# Type aliases for clean endpoint signatures (FastAPI official pattern)
TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]
SecurityValidatorDep = Annotated[SecurityValidator, Depends(get_security_validator)]
CommandExecutorDep = Annotated[CommandExecutor, Depends(get_command_executor)]
FileSystemServiceDep = Annotated[FileSystemService, Depends(get_filesystem_service)]
BorgVerificationServiceDep = Annotated[BorgVerificationService, Depends(get_borg_verification_service)]
RepositoryDataServiceDep = Annotated[RepositoryDataService, Depends(get_repository_data_service)]
RepositoryImportServiceDep = Annotated[RepositoryImportService, Depends(get_repository_import_service)]
RepositoryManagementServiceDep = Annotated[RepositoryManagementService, Depends(get_repository_management_service)]
RepositoryQueryServiceDep = Annotated[RepositoryQueryService, Depends(get_repository_query_service)]
JobExecutionServiceDep = Annotated[JobExecutionService, Depends(get_job_execution_service)]
JobManagementServiceDep = Annotated[JobManagementService, Depends(get_job_management_service)]
NotificationServiceDep = Annotated[NotificationServiceImpl, Depends(get_notification_service)]
TaskExecutionServiceDep = Annotated[TaskExecutionServiceImpl, Depends(get_task_execution_service)]
JobWorkflowServiceDep = Annotated[JobWorkflowServiceImpl, Depends(get_workflow_service)]
DatabaseDep = Annotated[Session, Depends(get_db)]