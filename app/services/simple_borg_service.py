"""
Simple Borg Service for basic operations without job management system.

This service handles simple borg operations (info, list, verify) directly
through command execution, making it easy to test and mock.
Complex operations (backup, prune) still use the full job management system.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

from app.models.database import Repository
from app.services.simple_command_runner import SimpleCommandRunner
from app.utils.security import build_secure_borg_command

logger = logging.getLogger(__name__)


class SimpleBorgService:
    """
    Simple Borg service for basic operations without job system complexity.
    
    This service is designed to be:
    - Easy to test (no job management dependencies)
    - Fast for simple operations 
    - Mockable for unit tests
    - Following single responsibility principle
    """
    
    def __init__(self, command_runner: Optional[SimpleCommandRunner] = None):
        self.command_runner = command_runner or SimpleCommandRunner()
    
    async def verify_repository_access(
        self, repo_path: str, passphrase: str, keyfile_path: str = None
    ) -> bool:
        """
        Verify repository access using direct command execution.
        
        This bypasses the job management system for simplicity and testability.
        """
        try:
            # Build environment overrides for keyfile if needed
            env_overrides = {}
            if keyfile_path:
                env_overrides["BORG_KEY_FILE"] = keyfile_path

            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repo_path,
                passphrase=passphrase,
                additional_args=["--json"],
                environment_overrides=env_overrides,
            )
        except Exception as e:
            logger.error(f"Security validation failed: {e}")
            return False

        try:
            # Use simple command runner for direct execution
            result = await self.command_runner.run_command(
                command=command,
                env=env,
                timeout=30
            )
            
            # Success if command returns 0
            success = result.return_code == 0
            
            if success:
                logger.debug(f"Repository verification succeeded for {repo_path}")
            else:
                logger.debug(f"Repository verification failed for {repo_path}: {result.stderr}")
                
            return success
            
        except Exception as e:
            logger.error(f"Repository verification failed: {e}")
            return False
    
    async def get_repository_info(self, repository: Repository) -> Optional[Dict]:
        """Get repository info using direct command execution."""
        try:
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )
            
            result = await self.command_runner.run_command(
                command=command,
                env=env,
                timeout=30
            )
            
            if result.return_code == 0:
                return json.loads(result.stdout.decode())
            else:
                logger.error(f"Failed to get repository info: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Repository info failed: {e}")
            return None
    
    async def list_archives_simple(self, repository: Repository) -> List[Dict]:
        """List archives using direct command execution."""
        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )
            
            result = await self.command_runner.run_command(
                command=command,
                env=env,
                timeout=60
            )
            
            if result.return_code == 0:
                return json.loads(result.stdout.decode()).get("archives", [])
            else:
                logger.error(f"Failed to list archives: {result.stderr}")
                return []
                
        except Exception as e:
            logger.error(f"Archive listing failed: {e}")
            return []