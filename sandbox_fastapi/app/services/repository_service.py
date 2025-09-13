"""
Repository service using real database operations with clean architecture.

This demonstrates proper SQLAlchemy 2.0 usage with FastAPI dependency injection.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.repository import Repository
from app.models.schemas import RepositoryCreate, RepositoryResponse
from app.services.interfaces import (
    SecurityValidator,
    RepositoryDataService,
    RepositoryValidationError
)

logger = logging.getLogger(__name__)


class SqlAlchemyRepositoryDataService:
    """
    Repository data service using real SQLAlchemy operations.
    
    Demonstrates proper SQLAlchemy 2.0 patterns with clean architecture.
    """
    
    def find_by_name(self, db: Session, name: str) -> Optional[Repository]:
        """Find repository by name using SQLAlchemy 2.0 select()."""
        stmt = select(Repository).where(Repository.name == name)
        return db.scalar(stmt)
    
    def find_by_path(self, db: Session, path: str) -> Optional[Repository]:
        """Find repository by path using SQLAlchemy 2.0 select()."""
        stmt = select(Repository).where(Repository.path == path)
        return db.scalar(stmt)
    
    def list_repositories(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Repository]:
        """List repositories with pagination using SQLAlchemy 2.0."""
        stmt = select(Repository).order_by(Repository.created_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt))
    
    def save(self, db: Session, repository: Repository) -> Repository:
        """Save repository using SQLAlchemy 2.0 session patterns."""
        db.add(repository)
        db.flush()  # Get ID without committing
        db.refresh(repository)
        return repository
    
    def delete(self, db: Session, repository: Repository) -> bool:
        """Delete repository using SQLAlchemy 2.0."""
        db.delete(repository)
        db.flush()
        return True


class RepositoryManagementService:
    """
    Repository management service with clean business logic.
    
    Demonstrates service layer separation with real database operations.
    """
    
    def __init__(
        self,
        security_validator: SecurityValidator,
        data_service: RepositoryDataService
    ):
        self.security_validator = security_validator
        self.data_service = data_service
    
    def list_repositories(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[RepositoryResponse]:
        """List repositories with business logic and validation."""
        # Validate pagination parameters
        if skip < 0:
            raise RepositoryValidationError("Skip parameter cannot be negative")
        if limit <= 0 or limit > 1000:
            raise RepositoryValidationError("Limit must be between 1 and 1000")
        
        # Get repositories from data layer
        repositories = self.data_service.list_repositories(db, skip, limit)
        
        # Convert to response models using Pydantic v2 pattern
        return [
            RepositoryResponse.model_validate(repo)
            for repo in repositories
        ]
    
    def create_repository(
        self,
        db: Session,
        repository_data: RepositoryCreate
    ) -> RepositoryResponse:
        """Create repository with validation and business logic."""
        # Validate inputs
        validated_name = self.security_validator.validate_repository_name(repository_data.name)
        validated_passphrase = self.security_validator.validate_passphrase(repository_data.passphrase)
        
        # Check for duplicates
        existing_name = self.data_service.find_by_name(db, validated_name)
        if existing_name:
            raise RepositoryValidationError(f"Repository with name '{validated_name}' already exists")
        
        existing_path = self.data_service.find_by_path(db, repository_data.path)
        if existing_path:
            raise RepositoryValidationError(f"Repository with path '{repository_data.path}' already exists")
        
        # Create repository
        repository = Repository(
            name=validated_name,
            path=repository_data.path
        )
        repository.set_passphrase(validated_passphrase)
        
        # Save to database
        saved_repository = self.data_service.save(db, repository)
        
        logger.info(f"Created repository: {validated_name}")
        
        return RepositoryResponse.model_validate(saved_repository)