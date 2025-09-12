"""
Service interfaces for clean dependency injection and testability.

These interfaces define contracts for core business operations, enabling:
- Clean separation of concerns between API and business logic
- Easy mocking and testing without complex setup
- Dependency injection for better maintainability
- Future implementation swapping
"""

from typing import Protocol, Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.models.database import Repository, User


class RepositoryQueryService(Protocol):
    """Interface for repository query operations."""
    
    def list_repositories(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Repository]:
        """
        List repositories with pagination.
        
        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of repository objects
        """
        ...


class SecurityValidator(Protocol):
    """Interface for security validation operations."""
    
    def validate_repository_name(self, name: str) -> str:
        """
        Validate and sanitize a repository name.
        
        Args:
            name: Repository name to validate
            
        Returns:
            Validated repository name
            
        Raises:
            ValueError: If name is invalid or contains dangerous characters
        """
        ...
    
    def sanitize_filename(self, filename: str, max_length: int = 100) -> str:
        """
        Sanitize a filename to remove dangerous characters.
        
        Args:
            filename: Filename to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Safe filename
        """
        ...
    
    def validate_passphrase(self, passphrase: str) -> str:
        """
        Validate passphrase for safe use in commands.
        
        Args:
            passphrase: Passphrase to validate
            
        Returns:
            Validated passphrase
            
        Raises:
            ValueError: If passphrase contains dangerous characters
        """
        ...


class BorgServiceInterface(Protocol):
    """Interface for Borg operations."""
    
    async def initialize_repository(self, repository: Repository) -> Dict[str, Any]:
        """
        Initialize a new Borg repository.
        
        Args:
            repository: Repository object with path and passphrase
            
        Returns:
            Result dictionary with success status and message
        """
        ...
    
    async def verify_repository_access(
        self, 
        repo_path: str, 
        passphrase: str, 
        keyfile_path: Optional[str] = None
    ) -> bool:
        """
        Verify access to an existing repository.
        
        Args:
            repo_path: Path to repository
            passphrase: Repository passphrase
            keyfile_path: Optional keyfile path
            
        Returns:
            True if access successful, False otherwise
        """
        ...
    
    async def list_archives(self, repository: Repository) -> List[Dict]:
        """
        List archives in a repository.
        
        Args:
            repository: Repository to list archives from
            
        Returns:
            List of archive information dictionaries
        """
        ...


class RepositoryService(Protocol):
    """Interface for repository business operations."""
    
    async def create_repository(
        self,
        name: str,
        path: str, 
        passphrase: str,
        user: User,
        db: Session,
        is_import: bool = False,
        keyfile_content: Optional[bytes] = None,
        keyfile_filename: Optional[str] = None
    ) -> Repository:
        """
        Create a new repository (either initialize or import existing).
        
        Args:
            name: Repository name
            path: Repository path
            passphrase: Repository passphrase
            user: Current user
            db: Database session
            is_import: Whether this is importing existing repo
            keyfile_content: Optional keyfile content for imported repos
            keyfile_filename: Optional keyfile filename for imported repos
            
        Returns:
            Created repository object
            
        Raises:
            ValueError: If validation fails
            RepositoryError: If creation/import fails
        """
        ...
    
    async def update_repository(
        self,
        repo_id: int,
        updates: Dict[str, Any],
        user: User,
        db: Session
    ) -> Repository:
        """
        Update an existing repository.
        
        Args:
            repo_id: Repository ID to update
            updates: Dictionary of fields to update
            user: Current user
            db: Database session
            
        Returns:
            Updated repository object
            
        Raises:
            ValueError: If validation fails
            RepositoryNotFoundError: If repository doesn't exist
        """
        ...
    
    def get_repository(self, repo_id: int, db: Session) -> Optional[Repository]:
        """
        Get repository by ID.
        
        Args:
            repo_id: Repository ID
            db: Database session
            
        Returns:
            Repository object or None if not found
        """
        ...
    
    async def delete_repository(
        self, 
        repo_id: int, 
        user: User, 
        db: Session,
        scheduler_service=None,
        delete_borg_repo: bool = False
    ) -> bool:
        """
        Delete a repository.
        
        Args:
            repo_id: Repository ID to delete
            user: Current user
            db: Database session
            
        Returns:
            True if deleted successfully
            
        Raises:
            RepositoryNotFoundError: If repository doesn't exist
        """
        ...


class RepositoryError(Exception):
    """Base exception for repository operations."""
    pass


class RepositoryNotFoundError(RepositoryError):
    """Raised when repository is not found."""
    pass


class RepositoryValidationError(RepositoryError):
    """Raised when repository validation fails."""
    pass