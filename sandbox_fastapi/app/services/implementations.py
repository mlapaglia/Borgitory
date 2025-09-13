"""
Clean service implementations demonstrating proper dependency injection.

These implementations follow single responsibility principle and use
constructor injection for clean, testable code.
"""

import subprocess
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.schemas import RepositoryImport, ImportResult, RepositoryResponse
from app.services.interfaces import (
    SecurityValidator,
    CommandExecutor, 
    BorgVerificationService,
    RepositoryDataService,
    RepositoryImportService,
    FileSystemService,
    CommandResult,
    RepositoryError,
    RepositoryValidationError,
    RepositoryVerificationError
)

logger = logging.getLogger(__name__)


class SimpleSecurityValidator:
    """Simple security validator implementation."""
    
    def validate_repository_name(self, name: str) -> str:
        """Validate repository name (simplified for sandbox)."""
        if not name or len(name.strip()) == 0:
            raise RepositoryValidationError("Repository name cannot be empty")
        
        if len(name) > 100:
            raise RepositoryValidationError("Repository name too long")
        
        # Check for dangerous characters
        dangerous_chars = ["../", "..\\", ";", "|", "&", "`", "$"]
        for char in dangerous_chars:
            if char in name:
                raise RepositoryValidationError(f"Repository name contains dangerous character: {char}")
        
        return name.strip()
    
    def validate_passphrase(self, passphrase: str) -> str:
        """Validate passphrase (simplified for sandbox)."""
        if not passphrase or len(passphrase.strip()) == 0:
            raise RepositoryValidationError("Passphrase cannot be empty")
        
        return passphrase
    
    def validate_path(self, path: str) -> str:
        """Validate and sanitize file path."""
        if not path or len(path.strip()) == 0:
            raise RepositoryValidationError("Path cannot be empty")
        
        # Check for path traversal attempts
        if ".." in path:
            raise RepositoryValidationError("Path cannot contain directory traversal")
        
        # For sandbox, allow common development paths
        path = path.strip()
        allowed_prefixes = ["/mnt/", "/tmp/", "/var/", "/home/", "C:", "D:"]
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
            raise RepositoryValidationError("Path must be an absolute path")
        
        return path
    
    def build_secure_borg_env(
        self,
        passphrase: str,
        keyfile_path: Optional[str] = None,
        additional_env: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build secure environment variables for Borg commands."""
        # Validate inputs
        validated_passphrase = self.validate_passphrase(passphrase)
        
        # Build environment variables
        environment = {
            "BORG_PASSPHRASE": validated_passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes",
            "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes",
        }
        
        # Add keyfile if provided
        if keyfile_path:
            validated_keyfile = self.validate_path(keyfile_path)
            environment["BORG_KEY_FILE"] = validated_keyfile
        
        # Add any additional environment variables
        if additional_env:
            for key, value in additional_env.items():
                if isinstance(key, str) and isinstance(value, str):
                    # Basic validation for env var names
                    if key.isalnum() or all(c in "_-" for c in key if not c.isalnum()):
                        environment[key] = value
        
        return environment


class SimpleCommandExecutor:
    """Simple command executor without complex job management."""
    
    async def run_command(
        self, 
        command: List[str], 
        env: Optional[dict] = None, 
        timeout: int = 30
    ) -> CommandResult:
        """Execute command directly (simplified for sandbox)."""
        try:
            # In a real implementation, this would execute the actual command
            # For sandbox, we'll simulate based on command
            logger.info(f"SANDBOX: Executing command: {' '.join(command[:3])}...")
            
            if "borg info" in ' '.join(command):
                # Simulate successful borg info
                return CommandResult(0, b'{"repository": {"id": "test-repo"}}', b'')
            elif "borg list" in ' '.join(command):
                # Simulate archive list
                return CommandResult(0, b'{"archives": [{"name": "test-archive"}]}', b'')
            else:
                # Unknown command
                return CommandResult(1, b'', b'Unknown command')
                
        except Exception as e:
            logger.exception(f"Command execution failed: {e}")
            return CommandResult(1, b'', str(e).encode())


class SimpleBorgVerificationService:
    """Simple Borg verification service using command executor."""
    
    def __init__(self, command_executor: CommandExecutor):
        self.command_executor = command_executor
    
    async def verify_repository_access(
        self,
        repo_path: str,
        passphrase: str,
        keyfile_content: Optional[bytes] = None
    ) -> bool:
        """Verify repository access using simple command execution."""
        try:
            # Build simple borg info command
            command = ["borg", "info", "--json", repo_path]
            env = {"BORG_PASSPHRASE": passphrase}
            
            if keyfile_content:
                # In real implementation, would save keyfile temporarily
                env["BORG_KEY_FILE"] = "/tmp/keyfile"
            
            result = await self.command_executor.run_command(command, env, timeout=30)
            
            if result.success:
                logger.info(f"Repository verification succeeded for {repo_path}")
                return True
            else:
                logger.warning(f"Repository verification failed for {repo_path}")
                return False
                
        except Exception as e:
            logger.error(f"Repository verification error: {e}")
            return False


class SimpleRepositoryDataService:
    """Simple repository data service using repository pattern."""
    
    def find_by_name(self, db: Session, name: str) -> Optional[Repository]:
        """Find repository by name."""
        return db.query(Repository).filter(Repository.name == name).first()
    
    def find_by_path(self, db: Session, path: str) -> Optional[Repository]:
        """Find repository by path.""" 
        return db.query(Repository).filter(Repository.path == path).first()
    
    def save(self, db: Session, repository: Repository) -> Repository:
        """Save repository to database."""
        db.add(repository)
        db.commit()
        db.refresh(repository)
        return repository
    
    def delete(self, db: Session, repository: Repository) -> bool:
        """Delete repository from database."""
        db.delete(repository)
        db.commit()
        return True


class RepositoryImportServiceImpl:
    """
    Repository import service with clean dependency injection.
    
    This demonstrates proper separation of concerns:
    - Security validation
    - Repository verification  
    - Database operations
    - Business logic coordination
    """
    
    def __init__(
        self,
        security_validator: SecurityValidator,
        borg_service: BorgVerificationService,
        data_service: RepositoryDataService
    ):
        self.security_validator = security_validator
        self.borg_service = borg_service
        self.data_service = data_service
    
    async def import_repository(
        self,
        import_data: RepositoryImport,
        db: Session
    ) -> ImportResult:
        """Import repository with complete business logic."""
        try:
            # Step 1: Validate inputs
            validated_name = self.security_validator.validate_repository_name(import_data.name)
            validated_passphrase = self.security_validator.validate_passphrase(import_data.passphrase)
            
            # Step 2: Check for duplicates
            existing_name = self.data_service.find_by_name(db, validated_name)
            if existing_name:
                raise RepositoryValidationError(f"Repository with name '{validated_name}' already exists")
            
            existing_path = self.data_service.find_by_path(db, import_data.path)
            if existing_path:
                raise RepositoryValidationError(f"Repository with path '{import_data.path}' already exists")
            
            # Step 3: Verify repository access
            verification_success = await self.borg_service.verify_repository_access(
                repo_path=import_data.path,
                passphrase=validated_passphrase,
                keyfile_content=import_data.keyfile_content
            )
            
            if not verification_success:
                raise RepositoryVerificationError("Failed to verify repository access")
            
            # Step 4: Create and save repository
            from datetime import datetime
            repository = Repository(
                name=validated_name,
                path=import_data.path,
                created_at=datetime.utcnow()
            )
            repository.set_passphrase(validated_passphrase)
            
            saved_repository = self.data_service.save(db, repository)
            
            logger.info(f"Successfully imported repository: {validated_name}")
            
            return ImportResult(
                success=True,
                repository=RepositoryResponse.model_validate(saved_repository),
                message=f"Repository '{validated_name}' imported successfully"
            )
            
        except (RepositoryValidationError, RepositoryVerificationError) as e:
            logger.error(f"Repository import failed: {e}")
            return ImportResult(
                success=False,
                repository=None,
                message=str(e)
            )
        except Exception as e:
            # Proper error handling with specific logging
            logger.exception(f"Unexpected error during repository import: {e}")
            return ImportResult(
                success=False,
                repository=None,
                message="An unexpected error occurred during import. Please check the logs for details."
            )


class SimpleFileSystemService:
    """Simple filesystem service implementation for path operations."""
    
    def exists(self, path: str) -> bool:
        """Check if path exists."""
        try:
            return Path(path).exists()
        except Exception:
            return False
    
    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        try:
            return Path(path).is_dir()
        except Exception:
            return False
        
    def list_directories(self, path: str, include_files: bool = False) -> List[Dict[str, Any]]:
        """List directory contents."""
        try:
            items = []
            path_obj = Path(path)
            
            if not path_obj.exists() or not path_obj.is_dir():
                return []
            
            for item in path_obj.iterdir():
                try:
                    if item.is_dir():
                        items.append({
                            "name": item.name,
                            "path": str(item),
                            "type": "directory"
                        })
                    elif include_files and item.is_file():
                        items.append({
                            "name": item.name,
                            "path": str(item),
                            "type": "file"
                        })
                except (PermissionError, OSError):
                    # Skip items we can't access
                    continue
            
            # Sort directories first, then by name
            items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
            return items[:50]  # Limit results for performance
            
        except Exception as e:
            logger.debug(f"Error listing directory {path}: {e}")
            return []
    
    def get_basename(self, path: str) -> str:
        """Get the basename of a path."""
        try:
            return Path(path).name
        except Exception:
            return ""
    
    def delete_file(self, path: str) -> bool:
        """Delete a file. Returns True if successful."""
        try:
            Path(path).unlink()
            return True
        except Exception as e:
            logger.debug(f"Failed to delete file {path}: {e}")
            return False