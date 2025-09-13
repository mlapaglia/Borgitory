"""
Repository query service for synchronous operations.

This service handles immediate repository operations where the frontend
waits for results (scanning, validation, directory listing).
"""

import asyncio
import configparser
import json
import logging
from datetime import datetime, UTC
from typing import List, Dict, Optional, Any

from app.services.interfaces import CommandExecutor, SecurityValidator, FileSystemService
from app.models.schemas import RepositoryScanResult, ValidationResult

logger = logging.getLogger(__name__)


class RepositoryQueryService:
    """
    Synchronous repository operations with timeout protection.
    
    Designed for operations where frontend needs immediate results:
    - Repository scanning
    - Path validation  
    - Quick verification
    - Directory listing
    """
    
    def __init__(
        self,
        command_executor: CommandExecutor,
        security_validator: SecurityValidator,
        filesystem_service: FileSystemService,
        default_timeout: int = 30
    ):
        self.command_executor = command_executor
        self.security_validator = security_validator
        self.filesystem_service = filesystem_service
        self.default_timeout = default_timeout
    
    async def scan_repositories(self, scan_path: str = "/mnt") -> List[RepositoryScanResult]:
        """
        Scan for existing Borg repositories.
        
        Returns immediate results with timeout protection.
        Frontend shows loading indicator during execution.
        """
        try:
            # Validate scan path
            validated_path = self.security_validator.validate_path(scan_path)
            
            # Quick directory check first
            if not self.filesystem_service.exists(validated_path):
                logger.warning(f"Scan path does not exist: {validated_path}")
                return []
            
            # Scan for potential repository directories
            repositories = []
            
            # Use find command to locate potential repo dirs (config file indicates borg repo)
            find_command = [
                "find", validated_path, 
                "-name", "config", 
                "-path", "*/config", 
                "-type", "f",
                "-exec", "dirname", "{}", ";"
            ]
            
            result = await asyncio.wait_for(
                self.command_executor.run_command(find_command),
                timeout=self.default_timeout
            )
            
            if result.return_code != 0:
                logger.error(f"Find command failed: {result.stderr}")
                return []
            
            # Parse potential repository paths
            potential_paths = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            # Verify each potential repository
            for repo_path in potential_paths:
                if not repo_path.strip():
                    continue
                    
                try:
                    # Quick borg info check with minimal timeout
                    info_result = await self._quick_repo_info(repo_path.strip())
                    if info_result:
                        repositories.append(info_result)
                        
                except asyncio.TimeoutError:
                    logger.debug(f"Repository check timed out for {repo_path}")
                    # Add as potential repository but mark as unverified
                    repositories.append(RepositoryScanResult(
                        path=repo_path.strip(),
                        name=self.filesystem_service.get_basename(repo_path.strip()),
                        encryption_mode="unknown",
                        requires_keyfile=False,
                        verified=False,
                        preview="Repository found but verification timed out"
                    ))
                except Exception as e:
                    logger.debug(f"Repository check failed for {repo_path}: {e}")
                    continue
            
            logger.info(f"Scan found {len(repositories)} repositories in {validated_path}")
            return repositories
            
        except asyncio.TimeoutError:
            logger.warning(f"Repository scan timed out for path: {scan_path}")
            raise TimeoutError("Repository scan is taking too long. Try a smaller directory.")
        except Exception as e:
            logger.error(f"Repository scan failed: {e}")
            raise
    
    async def _quick_repo_info(self, repo_path: str, timeout: int = 10) -> Optional[RepositoryScanResult]:
        """Quick repository info check with tight timeout."""
        try:
            # First check if directory structure looks like a repo
            if not self._looks_like_borg_repo(repo_path):
                return None
            
            # Parse config file for detailed information
            config_info = self.parse_borg_config(repo_path)
            
            # Skip if it's not a valid Borg repository
            if config_info["mode"] in ["invalid", "error"]:
                logger.debug(f"Skipping {repo_path}: {config_info['preview']}")
                return None
            
            repo_name = self.filesystem_service.get_basename(repo_path.strip())
            if not repo_name:
                repo_name = "unnamed_repository"
            
            # Try to get additional repository metadata
            try:
                metadata = await self._get_repository_metadata(repo_path)
            except Exception as e:
                logger.debug(f"Could not get metadata for {repo_path}: {e}")
                metadata = {}
            
            # Build preview with available information
            preview_parts = [config_info["preview"]]
            if metadata.get("size"):
                preview_parts.append(f"Size: {metadata['size']}")
            if metadata.get("last_backup"):
                try:
                    backup_time = datetime.fromisoformat(metadata["last_backup"].replace("Z", "+00:00"))
                    preview_parts.append(f"Last backup: {backup_time.strftime('%Y-%m-%d')}")
                except:
                    pass
            
            return RepositoryScanResult(
                path=repo_path,
                name=repo_name,
                encryption_mode=config_info["mode"],
                requires_keyfile=config_info["requires_keyfile"],
                verified=True,
                preview="; ".join(preview_parts)
            )
            
        except asyncio.TimeoutError:
            logger.debug(f"Repository check timed out for {repo_path}")
            raise
        except Exception as e:
            logger.debug(f"Quick repo info failed for {repo_path}: {e}")
            return None
    
    def _looks_like_borg_repo(self, repo_path: str) -> bool:
        """Check if directory structure looks like a Borg repository."""
        try:
            # Basic structure check using filesystem service
            return (
                self.filesystem_service.is_dir(repo_path) and
                self.filesystem_service.exists(repo_path + "/config") and
                self.filesystem_service.is_dir(repo_path + "/data")
            )
        except Exception:
            return False
    
    def parse_borg_config(self, repo_path: str) -> Dict[str, Any]:
        """Parse a Borg repository config file to determine encryption mode and details."""
        config_path = repo_path + "/config"
        
        try:
            if not self.filesystem_service.exists(config_path):
                return {
                    "mode": "unknown",
                    "requires_keyfile": False,
                    "preview": "Config file not found",
                }
            
            # Read config file content
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_content = f.read()
            except Exception as e:
                return {
                    "mode": "error", 
                    "requires_keyfile": False,
                    "preview": f"Cannot read config: {e}"
                }
            
            # Parse the config file (it's an INI-like format)
            config = configparser.ConfigParser()
            config.read_string(config_content)
            
            # Check if this looks like a Borg repository
            if not config.has_section("repository"):
                return {
                    "mode": "invalid",
                    "requires_keyfile": False,
                    "preview": "Not a valid Borg repository (no [repository] section)",
                }
            
            # Try to determine encryption mode from various indicators
            mode = "unknown"
            requires_keyfile = False
            preview_parts = []
            
            # Check for key-type file
            key_type_file = repo_path + "/key-type"
            if self.filesystem_service.exists(key_type_file):
                try:
                    with open(key_type_file, "r", encoding="utf-8") as f:
                        key_type = f.read().strip()
                        logger.info(f"Key type: {key_type}")
                        preview_parts.append(f"Key type: {key_type}")
                        
                        if key_type in [
                            "blake2-chacha20-poly1305",
                            "argon2-chacha20-poly1305",
                        ]:
                            mode = "repokey"
                            requires_keyfile = False  # Passphrase mode
                        elif key_type in [
                            "blake2-aes256-ctr-hmac-sha256", 
                            "argon2-aes256-ctr-hmac-sha256",
                        ]:
                            mode = "keyfile" 
                            requires_keyfile = True  # Key file mode
                        else:
                            mode = "encrypted"
                            requires_keyfile = False  # Assume passphrase by default
                except Exception as e:
                    logger.warning(f"Could not read key-type file: {e}")
                    preview_parts.append(f"Could not read key-type: {e}")
            
            # Check security directory
            security_dir = repo_path + "/security"
            if self.filesystem_service.exists(security_dir) and self.filesystem_service.is_dir(security_dir):
                try:
                    security_items = self.filesystem_service.list_directories(security_dir, include_files=True)
                    logger.info(f"Security directory contents: {len(security_items)} items")
                    preview_parts.append(f"Security files: {len(security_items)} items")
                    
                    if mode == "unknown":
                        if security_items:
                            mode = "repokey"
                            requires_keyfile = False  # Security dir usually means passphrase
                        else:
                            mode = "unencrypted"
                            requires_keyfile = False
                except Exception as e:
                    logger.warning(f"Could not read security directory: {e}")
                    preview_parts.append(f"Security directory error: {e}")
            
            # If we still don't know, make an educated guess
            if mode == "unknown":
                if self.filesystem_service.exists(security_dir) or self.filesystem_service.exists(key_type_file):
                    mode = "encrypted"
                    requires_keyfile = False
                else:
                    mode = "unencrypted" 
                    requires_keyfile = False
            
            # Get repository info from config if available
            if config.has_section("repository"):
                try:
                    repo_section = config["repository"]
                    if "version" in repo_section:
                        preview_parts.append(f"Version: {repo_section['version']}")
                    if "segments_per_dir" in repo_section:
                        preview_parts.append(f"Segments per dir: {repo_section['segments_per_dir']}")
                except Exception as e:
                    logger.warning(f"Could not read repository section: {e}")
            
            preview = (
                "; ".join(preview_parts)
                if preview_parts
                else f"Borg repository detected ({mode})"
            )
            
            return {
                "mode": mode,
                "requires_keyfile": requires_keyfile, 
                "preview": preview,
            }
            
        except Exception as e:
            logger.error(f"Error parsing Borg config at {config_path}: {e}")
            return {
                "mode": "error",
                "requires_keyfile": False,
                "preview": f"Parse error: {str(e)}",
            }
    
    async def _get_repository_metadata(self, repo_path: str) -> Dict[str, Any]:
        """Try to get additional metadata about a repository (size, last backup, etc.)"""
        metadata = {}
        
        try:
            # Try to get repository size
            if self.filesystem_service.exists(repo_path):
                # Use du to get directory size
                result = await self.command_executor.run_command(
                    ["du", "-sh", repo_path],
                    timeout=10,  # Quick timeout
                )
                if result.return_code == 0 and result.stdout:
                    size_line = result.stdout.strip().split("\t")[0]
                    metadata["size"] = size_line
        except Exception as e:
            logger.debug(f"Could not get size for {repo_path}: {e}")
        
        # Try to determine last backup time from directory timestamps
        try:
            data_dir = repo_path + "/data"
            if self.filesystem_service.exists(data_dir) and self.filesystem_service.is_dir(data_dir):
                # Get the most recent modification time in the data directory
                import os
                latest_mtime = 0
                for root, dirs, files in os.walk(data_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            mtime = os.path.getmtime(file_path)
                            if mtime > latest_mtime:
                                latest_mtime = mtime
                        except OSError:
                            continue
                
                if latest_mtime > 0:
                    metadata["last_backup"] = datetime.fromtimestamp(
                        latest_mtime, UTC
                    ).isoformat()
        except Exception as e:
            logger.debug(f"Could not get last backup time for {repo_path}: {e}")
        
        return metadata
    
    async def validate_repository_import(
        self,
        repo_path: str,
        passphrase: str,
        keyfile_content: Optional[bytes] = None
    ) -> ValidationResult:
        """
        Validate repository for import with credentials.
        
        Quick validation - frontend waits for result.
        """
        try:
            # Security validation
            validated_path = self.security_validator.validate_path(repo_path)
            validated_passphrase = self.security_validator.validate_passphrase(passphrase)
            
            # Handle keyfile if provided
            keyfile_path = None
            if keyfile_content:
                # Save keyfile temporarily for validation
                keyfile_path = f"/tmp/borg_keyfile_{datetime.now().timestamp()}"
                with open(keyfile_path, "wb") as f:
                    f.write(keyfile_content)
            
            # Build secure environment using security validator
            env = self.security_validator.build_secure_borg_env(
                passphrase=validated_passphrase,
                keyfile_path=keyfile_path
            )
            
            try:
                # Quick borg info with credentials
                info_command = ["borg", "info", "--json", validated_path]
                
                result = await asyncio.wait_for(
                    self.command_executor.run_command(info_command, env=env),
                    timeout=15  # Shorter timeout for validation
                )
                
                success = result.return_code == 0
                
                if success and result.stdout:
                    try:
                        info_data = json.loads(result.stdout)
                        return ValidationResult(
                            is_valid=True,
                            message="Repository validation successful",
                            repository_info={
                                "encryption": info_data.get('encryption', {}),
                                "cache": info_data.get('cache', {}),
                                "repository": info_data.get('repository', {})
                            }
                        )
                    except json.JSONDecodeError:
                        pass
                
                return ValidationResult(
                    is_valid=False,
                    message=f"Repository validation failed: {result.stderr.strip() if result.stderr else 'Unknown error'}"
                )
                
            finally:
                # Clean up temporary keyfile
                if keyfile_path and self.filesystem_service.exists(keyfile_path):
                    if not self.filesystem_service.delete_file(keyfile_path):
                        logger.warning(f"Failed to clean up keyfile: {keyfile_path}")
                        
        except asyncio.TimeoutError:
            return ValidationResult(
                is_valid=False,
                message="Repository validation timed out. Repository may be slow to access."
            )
        except Exception as e:
            logger.error(f"Repository validation failed: {e}")
            return ValidationResult(
                is_valid=False,
                message=f"Validation error: {str(e)}"
            )
    
    def list_directories(self, path: str, include_files: bool = False) -> List[Dict[str, Any]]:
        """
        List directories for path autocomplete.
        
        Quick operation for UI responsiveness.
        """
        try:
            # Security validation
            validated_path = self.security_validator.validate_path(path)
            
            if not self.filesystem_service.exists(validated_path):
                return []
            
            if not self.filesystem_service.is_dir(validated_path):
                return []
            
            # Use filesystem service to list directory contents
            return self.filesystem_service.list_directories(validated_path, include_files)
            
        except Exception as e:
            logger.debug(f"Directory listing failed for {path}: {e}")
            return []