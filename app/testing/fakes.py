"""
Fake implementations for testing following 2024 best practices.

These are 'fakes' not 'mocks' - they have working implementations
that behave naturally but are simplified for testing.
"""

import logging
from typing import Dict, Any, List, Optional
from app.models.database import Repository
from app.services.interfaces import BorgServiceInterface

logger = logging.getLogger(__name__)


class FakeBorgService:
    """
    Fake Borg service implementation following 2024 best practices.
    
    This is a 'fake' that behaves like the real BorgService but:
    - Always succeeds (configurable)
    - Uses in-memory state instead of external processes
    - Simulates real behavior patterns
    - Provides deterministic results for testing
    """
    
    def __init__(
        self, 
        should_verify_success: bool = True,
        should_init_success: bool = True,
        should_list_success: bool = True
    ):
        # Configurable behavior for different test scenarios
        self.should_verify_success = should_verify_success
        self.should_init_success = should_init_success  
        self.should_list_success = should_list_success
        
        # Track calls for test verification (like real service would log)
        self.verification_calls = []
        self.initialization_calls = []
        self.list_archive_calls = []
        
        # Simulate repository state
        self.initialized_repositories = set()
        self.repository_archives = {}  # repo_path -> list of archives
    
    async def verify_repository_access(
        self, 
        repo_path: str, 
        passphrase: str, 
        keyfile_path: Optional[str] = None
    ) -> bool:
        """Fake repository access verification."""
        self.verification_calls.append({
            'repo_path': repo_path,
            'passphrase': passphrase, 
            'keyfile_path': keyfile_path
        })
        
        if not self.should_verify_success:
            logger.debug(f"FAKE: Repository verification failed for {repo_path}")
            return False
            
        logger.debug(f"FAKE: Repository verification succeeded for {repo_path}")
        return True
    
    async def initialize_repository(self, repository: Repository) -> Dict[str, Any]:
        """Fake repository initialization."""
        self.initialization_calls.append({
            'name': repository.name,
            'path': repository.path
        })
        
        if not self.should_init_success:
            error_messages = [
                "Permission denied",
                "Read-only file system", 
                "Repository already exists",
                "Invalid path"
            ]
            # Return different errors for testing different scenarios
            error_msg = error_messages[len(self.initialization_calls) % len(error_messages)]
            logger.debug(f"FAKE: Repository initialization failed for {repository.name}: {error_msg}")
            return {"success": False, "message": error_msg}
        
        # Simulate successful initialization
        self.initialized_repositories.add(repository.path)
        logger.debug(f"FAKE: Repository initialized successfully: {repository.name}")
        return {"success": True, "message": "Repository initialized successfully"}
    
    async def list_archives(self, repository: Repository) -> List[Dict]:
        """Fake archive listing."""
        self.list_archive_calls.append({
            'name': repository.name,
            'path': repository.path
        })
        
        if not self.should_list_success:
            raise Exception("Failed to list archives")
        
        # Return realistic fake archive data
        fake_archives = self.repository_archives.get(repository.path, [
            {
                "name": f"backup-2024-01-01_10-00-00",
                "time": "2024-01-01T10:00:00Z",
                "stats": {"original_size": 1024*1024*100}  # 100MB
            },
            {
                "name": f"backup-2024-01-02_10-00-00", 
                "time": "2024-01-02T10:00:00Z",
                "stats": {"original_size": 1024*1024*150}  # 150MB
            }
        ])
        
        logger.debug(f"FAKE: Listed {len(fake_archives)} archives for {repository.name}")
        return fake_archives
    
    def add_fake_archives(self, repo_path: str, archives: List[Dict]):
        """Add fake archives for a repository (for testing specific scenarios)."""
        self.repository_archives[repo_path] = archives
    
    def get_call_summary(self) -> Dict[str, int]:
        """Get summary of calls made (useful for test assertions)."""
        return {
            'verify_calls': len(self.verification_calls),
            'init_calls': len(self.initialization_calls), 
            'list_calls': len(self.list_archive_calls)
        }
    
    def reset_state(self):
        """Reset all state (useful between tests)."""
        self.verification_calls.clear()
        self.initialization_calls.clear()
        self.list_archive_calls.clear()
        self.initialized_repositories.clear()
        self.repository_archives.clear()