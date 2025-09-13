"""
Fake implementations for testing following 2024 best practices.

These are 'fakes' not 'mocks' - they have working implementations
that behave naturally but are simplified for testing.
"""

from typing import Optional, List
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.services.interfaces import (
    SecurityValidator,
    CommandExecutor,
    BorgVerificationService,
    RepositoryDataService,
    CommandResult,
    RepositoryValidationError
)


class FakeSecurityValidator:
    """Fake security validator for testing."""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.validated_names = []
        self.validated_passphrases = []
    
    def validate_repository_name(self, name: str) -> str:
        if self.should_fail:
            raise RepositoryValidationError("Fake validation failure")
        self.validated_names.append(name)
        return name
    
    def validate_passphrase(self, passphrase: str) -> str:
        if self.should_fail:
            raise RepositoryValidationError("Fake passphrase validation failure")
        self.validated_passphrases.append(passphrase)
        return passphrase


class FakeCommandExecutor:
    """Fake command executor that simulates command results."""
    
    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.executed_commands = []
    
    async def execute_command(
        self, 
        command: List[str], 
        env: dict, 
        timeout: int = 30
    ) -> CommandResult:
        self.executed_commands.append({
            'command': command,
            'env': env,
            'timeout': timeout
        })
        
        if self.should_succeed:
            return CommandResult(0, b'{"repository": {"id": "fake-success"}}', b'')
        else:
            return CommandResult(1, b'', b'Fake command failure')


class FakeBorgVerificationService:
    """Fake Borg verification service with configurable behavior."""
    
    def __init__(self, should_verify_success: bool = True):
        self.should_verify_success = should_verify_success
        self.verification_calls = []
    
    async def verify_repository_access(
        self,
        repo_path: str,
        passphrase: str,
        keyfile_content: Optional[bytes] = None
    ) -> bool:
        self.verification_calls.append({
            'repo_path': repo_path,
            'passphrase': passphrase,
            'has_keyfile': keyfile_content is not None
        })
        return self.should_verify_success


class FakeRepositoryDataService:
    """Fake repository data service using in-memory storage."""
    
    def __init__(self):
        self.repositories = {}  # name -> Repository
        self.paths = {}  # path -> Repository
        self.next_id = 1
    
    def find_by_name(self, db: Session, name: str) -> Optional[Repository]:
        return self.repositories.get(name)
    
    def find_by_path(self, db: Session, path: str) -> Optional[Repository]:
        return self.paths.get(path)
    
    def save(self, db: Session, repository: Repository) -> Repository:
        if repository.id is None:
            repository.id = self.next_id
            self.next_id += 1
        
        self.repositories[repository.name] = repository
        self.paths[repository.path] = repository
        return repository
    
    def delete(self, db: Session, repository: Repository) -> bool:
        if repository.name in self.repositories:
            del self.repositories[repository.name]
        if repository.path in self.paths:
            del self.paths[repository.path]
        return True
    
    def clear(self):
        """Clear all data (useful for test cleanup)."""
        self.repositories.clear()
        self.paths.clear()
        self.next_id = 1