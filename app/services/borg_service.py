import asyncio
import json
import re
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.database import Repository, Job, get_db
from app.services.docker_service import docker_service


class BorgService:
    def __init__(self):
        self.progress_pattern = re.compile(
            r'(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+'
            r'(?P<nfiles>\d+)\s+(?P<path>.*)'
        )
    
    async def initialize_repository(self, repository: Repository, encryption: str = "repokey") -> Dict:
        """Initialize a new Borg repository if it doesn't exist"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Initializing Borg repository at {repository.path}")
        
        passphrase = repository.get_passphrase()
        
        command = [
            "sh", "-c", 
            f"BORG_PASSPHRASE='{passphrase}' BORG_RELOCATED_REPO_ACCESS_IS_OK=yes borg init --encryption {encryption} {repository.path}"
        ]
        
        environment = {
            "BORG_PASSPHRASE": passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"
        }
        
        try:
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                name=f"borg-init-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            logger.info(f"Repository initialization container started: {container.id}")
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            logger.info(f"Init container finished with exit code: {exit_code}")
            
            if exit_code == 0 or exit_code == 143:
                return {
                    "success": True,
                    "message": "Repository initialized successfully",
                    "output": output
                }
            else:
                if "already exists" in output.lower():
                    logger.info("Repository already exists, which is fine")
                    return {
                        "success": True,
                        "message": "Repository already exists",
                        "output": output
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Repository initialization failed (exit code {exit_code})",
                        "output": output
                    }
                    
        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            return {
                "success": False,
                "message": f"Failed to initialize repository: {str(e)}",
                "output": ""
            }
    
    async def create_backup(
        self, 
        repository: Repository, 
        source_path: str = "/data",
        compression: str = "zstd",
        dry_run: bool = False
    ) -> AsyncGenerator[Dict, None]:
        """Create a backup and yield progress updates"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Creating backup for repository: {repository.name} at {repository.path}")
        logger.info(f"Source: {source_path}, Compression: {compression}, Dry run: {dry_run}")
        
        archive_name = f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.info(f"Archive name: {archive_name}")
        
        logger.info("Setting up environment variables...")
        try:
            passphrase = repository.get_passphrase()
            logger.info("Retrieved repository passphrase successfully")
        except Exception as e:
            logger.error(f"Failed to get repository passphrase: {e}")
            raise
        
        borg_cmd = f"borg create --stats --progress --json --compression={compression}"
        if dry_run:
            borg_cmd += " --dry-run"
        borg_cmd += f" {repository.path}::{archive_name} {source_path}"
        
        command = [
            "sh", "-c",
            f"BORG_PASSPHRASE='{passphrase}' BORG_RELOCATED_REPO_ACCESS_IS_OK=yes BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes {borg_cmd}"
        ]
        
        environment = {
            "BORG_PASSPHRASE": passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes",
            "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes"
        }
        logger.info("Environment variables set up successfully")
        
        logger.info(f"Using source path: {source_path}")
        volumes = None
        logger.info("Volume mapping handled automatically by docker_service")
        
        try:
            logger.info(f"Starting Borg container with command: {' '.join(command)}")
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                volumes=volumes,
                name=f"borg-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            logger.info(f"Container started successfully: {container.id}")
            
            yield {
                "type": "started",
                "container_id": container.id,
                "archive_name": archive_name
            }
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            yield {
                "type": "completed", 
                "exit_code": exit_code,
                "status": "success" if status["exit_code"] in [0, 143] else "failed"
            }
            
        except Exception as e:
            logger.error(f"Exception in create_backup: {type(e).__name__}: {str(e)}")
            logger.error(f"Exception details: {e.__class__.__module__}.{e.__class__.__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            yield {
                "type": "error",
                "message": f"{type(e).__name__}: {str(e)}"
            }
    
    async def list_archives(self, repository: Repository) -> List[Dict]:
        """List all archives in a repository"""
        passphrase = repository.get_passphrase()
        command = [
            "sh", "-c",
            f"BORG_PASSPHRASE='{passphrase}' BORG_RELOCATED_REPO_ACCESS_IS_OK=yes borg list --json {repository.path}"
        ]
        
        environment = {
            "BORG_PASSPHRASE": passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"
        }
        
        try:
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                name=f"borg-list-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            if exit_code in [0, 143]:
                try:
                    import logging
                    logger = logging.getLogger(__name__)
                    
                    # Extract the JSON part from the output
                    # Look for the start of JSON (first '{') and end of JSON (last '}')
                    json_start = output.find('{')
                    json_end = output.rfind('}')
                    
                    if json_start != -1 and json_end != -1 and json_end > json_start:
                        json_content = output[json_start:json_end+1]
                        
                        try:
                            data = json.loads(json_content)
                            if "archives" in data:
                                return data["archives"]
                        except json.JSONDecodeError as je:
                            logger.error(f"JSON decode error: {je}")
                    
                    # Fallback: return empty list if no valid JSON found
                    return []
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error parsing archive list output: {e}")
                    return []
            else:
                raise Exception(f"Borg list failed with exit code {exit_code}")
                
        except Exception as e:
            raise Exception(f"Failed to list archives: {str(e)}")
    
    async def verify_repository_access(self, repo_path: str, passphrase: str, keyfile_path: str = None) -> bool:
        """Verify that we can access a repository with the given credentials"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Build the borg command to test access
        command = [
            "sh", "-c",
            f"BORG_PASSPHRASE='{passphrase}' BORG_RELOCATED_REPO_ACCESS_IS_OK=yes borg list --json {repo_path}"
        ]
        
        environment = {
            "BORG_PASSPHRASE": passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"
        }
        
        # TODO: Add keyfile support when keyfile_path is provided
        if keyfile_path:
            logger.warning("Keyfile verification not yet implemented")
        
        try:
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                name=f"borg-verify-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            logger.info(f"Repository verification for {repo_path}: exit_code={exit_code}")
            logger.info(f"Repository verification output: {output[:500]}...")
            
            # Only exit code 0 indicates success for verification
            if status["exit_code"] == 0:
                try:
                    # Try to parse as JSON to ensure it's valid
                    json_start = output.find('{')
                    json_end = output.rfind('}')
                    
                    if json_start != -1 and json_end != -1 and json_end > json_start:
                        json_content = output[json_start:json_end+1]
                        import json
                        data = json.loads(json_content)
                        logger.info(f"Repository verification successful for {repo_path}")
                        return True
                    else:
                        logger.warning(f"No valid JSON found in output, verification failed")
                        return False
                except Exception as parse_error:
                    logger.warning(f"Could not parse borg output: {parse_error}")
                    return False
            else:
                logger.warning(f"Repository verification failed for {repo_path} with exit code {exit_code}: {output}")
                return False
                
        except Exception as e:
            logger.error(f"Repository verification error for {repo_path}: {e}")
            return False
    
    async def get_repo_info(self, repository: Repository) -> Dict:
        """Get repository information"""
        passphrase = repository.get_passphrase()
        command = [
            "sh", "-c",
            f"BORG_PASSPHRASE='{passphrase}' BORG_RELOCATED_REPO_ACCESS_IS_OK=yes borg info --json {repository.path}"
        ]
        
        environment = {
            "BORG_PASSPHRASE": passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"
        }
        
        try:
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                name=f"borg-info-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            if exit_code == 0:
                try:
                    return json.loads(output)
                except json.JSONDecodeError:
                    return {}
            else:
                raise Exception(f"Borg info failed with exit code {exit_code}")
                
        except Exception as e:
            raise Exception(f"Failed to get repo info: {str(e)}")
    
    def parse_progress_line(self, line: str) -> Optional[Dict]:
        """Parse Borg progress output"""
        if "Original size:" in line:
            # Parse final statistics
            parts = line.split()
            try:
                return {
                    "original_size": parts[2],
                    "compressed_size": parts[5],
                    "deduplicated_size": parts[8]
                }
            except (IndexError, ValueError):
                pass
        
        match = self.progress_pattern.search(line)
        if match:
            return {
                "original_size": int(match.group("original_size")),
                "compressed_size": int(match.group("compressed_size")),
                "deduplicated_size": int(match.group("deduplicated_size")),
                "nfiles": int(match.group("nfiles")),
                "current_path": match.group("path")
            }
        
        return None
    
    async def list_archive_contents(self, repository: Repository, archive_name: str) -> List[Dict]:
        """List the contents of a specific archive"""
        passphrase = repository.get_passphrase()
        command = [
            "sh", "-c",
            f"BORG_PASSPHRASE='{passphrase}' BORG_RELOCATED_REPO_ACCESS_IS_OK=yes borg list --json-lines {repository.path}::{archive_name}"
        ]
        
        environment = {
            "BORG_PASSPHRASE": passphrase,
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"
        }
        
        try:
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                name=f"borg-list-contents-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            if exit_code in [0, 143]:
                try:
                    # Parse JSON lines output
                    files = []
                    for line in output.strip().split('\n'):
                        if line.strip():
                            try:
                                file_info = json.loads(line)
                                files.append(file_info)
                            except json.JSONDecodeError:
                                continue
                    return files
                except Exception as e:
                    raise Exception(f"Failed to parse archive contents: {str(e)}")
            else:
                raise Exception(f"Borg list failed with exit code {exit_code}")
                
        except Exception as e:
            raise Exception(f"Failed to list archive contents: {str(e)}")
    
    async def scan_for_repositories(self, scan_path: str = "/repos") -> List[Dict]:
        """Scan a directory for existing Borg repositories"""
        import logging
        logger = logging.getLogger(__name__)
        
        command = [
            "sh", "-c",
            f"find {scan_path} -name 'config' -type f -exec sh -c 'if grep -q \"\\[repository\\]\" \"$1\" 2>/dev/null; then dirname \"$1\"; fi' _ {{}} \\; 2>/dev/null"
        ]
        
        environment = {}
        
        try:
            container = await docker_service.run_borg_container(
                command=command,
                environment=environment,
                name=f"borg-scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            logger.info(f"Repository scan completed with exit code {exit_code}, output: {output[:500]}...")
            
            if status["exit_code"] in [0, 143]:
                repo_paths = []
                for line in output.strip().split('\n'):
                    line = line.strip()
                    if (line and 
                        line.startswith('/') and  # Must be an absolute path
                        not line.startswith('[') and  # Ignore Docker/container messages
                        'exit code' not in line.lower() and  # Ignore exit code messages
                        'exception' not in line.lower() and  # Ignore exception messages
                        len(line) > 1):  # Must be more than just '/'
                        
                        logger.info(f"Found potential repository path: {line}")
                        repo_info = await self._get_repository_basic_info(line)
                        if repo_info:
                            repo_paths.append(repo_info)
                
                logger.info(f"Successfully identified {len(repo_paths)} repositories")
                return repo_paths
            else:
                logger.error(f"Repository scan failed with exit code {exit_code}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to scan for repositories: {e}")
            return []
    
    async def _get_repository_basic_info(self, repo_path: str) -> Optional[Dict]:
        """Get basic info about a repository without requiring passphrase"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # First, check if it's a valid repository by looking for the config file
            config_check_command = [
                "sh", "-c", 
                f"if [ -f '{repo_path}/config' ]; then echo 'REPO_EXISTS'; else echo 'NO_REPO'; fi"
            ]
            
            container = await docker_service.run_borg_container(
                command=config_check_command,
                environment={},
                name=f"borg-check-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {output}")
            
            
            if status["exit_code"] not in [0, 143] or "REPO_EXISTS" not in output:
                logger.warning(f"Repository not found or invalid at {repo_path}")
                return None
            
            # Run both borg info and config parsing in a single container
            combined_command = [
                "sh", "-c",
                f"echo '=== BORG_INFO_START ==='; "
                f"borg info '{repo_path}' 2>&1 || echo 'INFO_FAILED'; "
                f"echo '=== BORG_INFO_END ==='; "
                f"echo '=== CONFIG_ID_START ==='; "
                f"grep '^id = ' '{repo_path}/config' 2>/dev/null || echo 'NO_ID'; "
                f"echo '=== CONFIG_ID_END ==='"
            ]
            
            container = await docker_service.run_borg_container(
                command=combined_command,
                environment={},
                name=f"borg-info-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            
            loop = asyncio.get_event_loop()
            
            exit_code = await loop.run_in_executor(None, lambda: container.wait()['StatusCode'])
            
            combined_output = await loop.run_in_executor(None, lambda: container.logs().decode('utf-8'))
            logger.info(f"Container output: {combined_output}")
            
            # Parse borg info output for encryption information
            info_start = combined_output.find("=== BORG_INFO_START ===")
            info_end = combined_output.find("=== BORG_INFO_END ===")
            info_output = ""
            if info_start != -1 and info_end != -1:
                info_output = combined_output[info_start:info_end]
            
            # Parse config ID output
            id_start = combined_output.find("=== CONFIG_ID_START ===")
            id_end = combined_output.find("=== CONFIG_ID_END ===")
            id_output = ""
            if id_start != -1 and id_end != -1:
                id_output = combined_output[id_start:id_end]
            
            # Extract encryption information from the error messages or output
            encryption_mode = 'unknown'
            requires_keyfile = False
            repo_id = None
            
            # Look for encryption indicators in the borg info output
            if 'passphrase' in info_output.lower() and 'keyfile' not in info_output.lower():
                encryption_mode = 'repokey'
                requires_keyfile = False
            elif 'keyfile' in info_output.lower():
                encryption_mode = 'keyfile'  
                requires_keyfile = True
            elif 'unencrypted' in info_output.lower():
                encryption_mode = 'none'
                requires_keyfile = False
            else:
                # If we can't determine from borg info, assume repokey (most common default)
                # for repositories that exist and have valid config files
                encryption_mode = 'repokey'
                requires_keyfile = False
                logger.info(f"Could not determine encryption from borg output, defaulting to repokey for {repo_path}")
            
            # Extract repository ID from config output
            for line in id_output.split('\n'):
                if 'id = ' in line:
                    repo_id = line.split('=', 1)[1].strip()
                    break
            
            logger.info(f"Repository {repo_path}: encryption_mode={encryption_mode}, requires_keyfile={requires_keyfile}, id={repo_id[:8] if repo_id else 'unknown'}...")
            
            return {
                "path": repo_path,
                "id": repo_id,
                "encryption_mode": encryption_mode,
                "requires_keyfile": requires_keyfile,
                "detected": True,
                "config_preview": f"Repository detected with {encryption_mode} encryption"
            }
            
        except Exception as e:
            logger.error(f"Error getting repository info for {repo_path}: {e}")
            return None


borg_service = BorgService()