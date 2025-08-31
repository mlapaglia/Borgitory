import asyncio
import json
import logging
import re
import os
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.database import Repository, Job, get_db
from app.services.job_manager import borg_job_manager
from app.utils.security import (
    build_secure_borg_command, 
    validate_archive_name, 
    validate_compression,
    sanitize_path
)

logger = logging.getLogger(__name__)


class BorgService:
    def __init__(self):
        self.progress_pattern = re.compile(
            r'(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+'
            r'(?P<nfiles>\d+)\s+(?P<path>.*)'
        )
    
    def _parse_borg_config(self, repo_path: str) -> Dict[str, any]:
        """Parse a Borg repository config file to determine encryption mode"""
        config_path = os.path.join(repo_path, "config")
        
        try:
            if not os.path.exists(config_path):
                return {
                    "mode": "unknown",
                    "requires_keyfile": False,
                    "preview": "Config file not found"
                }
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
            
            # Parse the config file (it's an INI-like format)
            import configparser
            config = configparser.ConfigParser()
            config.read_string(config_content)
            
            # Debug: log the actual config content to understand structure
            logger.info(f"Parsing Borg config at {config_path}")
            logger.info(f"Sections found: {config.sections()}")
            
            # Check if this looks like a Borg repository
            if not config.has_section('repository'):
                return {
                    "mode": "invalid",
                    "requires_keyfile": False,
                    "preview": "Not a valid Borg repository (no [repository] section)"
                }
            
            # Log all options in repository section
            if config.has_section('repository'):
                repo_options = dict(config.items('repository'))
                logger.info(f"Repository section options: {repo_options}")
            
            # The key insight: Borg stores encryption info differently
            # Check for a key file in the repository directory
            key_files = []
            try:
                for item in os.listdir(repo_path):
                    if item.startswith('key.') or 'key' in item.lower():
                        key_files.append(item)
            except:
                pass
            
            # Method 1: Check for repokey data in config
            encryption_mode = "unknown"
            requires_keyfile = False
            preview = "Repository detected"
            
            # Look for key-related sections
            key_sections = [s for s in config.sections() if 'key' in s.lower()]
            logger.info(f"Key-related sections: {key_sections}")
            
            # Check repository section for encryption hints
            repo_section = dict(config.items('repository'))
            
            # Check for encryption by looking for the 'key' field in repository section
            if 'key' in repo_section:
                # Repository has a key field - this means it's encrypted
                key_value = repo_section['key']
                
                if key_value and len(key_value) > 50:  # Key data is present and substantial
                    # This is repokey mode - key is embedded in the repository
                    encryption_mode = "repokey"
                    requires_keyfile = False
                    preview = "Encrypted repository (repokey mode) - key embedded in repository"
                else:
                    # Key field exists but might be empty/reference - possibly keyfile mode
                    if key_files:
                        encryption_mode = "keyfile"
                        requires_keyfile = True
                        preview = f"Encrypted repository (keyfile mode) - found key files: {', '.join(key_files)}"
                    else:
                        encryption_mode = "encrypted"
                        requires_keyfile = False
                        preview = "Encrypted repository (key field present but unclear mode)"
            elif key_files:
                # No key in config but key files found - definitely keyfile mode
                encryption_mode = "keyfile"
                requires_keyfile = True
                preview = f"Encrypted repository (keyfile mode) - found key files: {', '.join(key_files)}"
            else:
                # No key field and no key files - check for other encryption indicators
                all_content_lower = config_content.lower()
                if any(word in all_content_lower for word in ['encrypt', 'cipher', 'algorithm', 'blake2', 'aes']):
                    encryption_mode = "encrypted"
                    requires_keyfile = False
                    preview = "Encrypted repository (encryption detected but mode unclear)"
                else:
                    # Likely unencrypted (very rare for Borg)
                    encryption_mode = "none"
                    requires_keyfile = False
                    preview = "Unencrypted repository (no encryption detected)"
            
            return {
                "mode": encryption_mode,
                "requires_keyfile": requires_keyfile,
                "preview": preview
            }
            
        except Exception as e:
            logger.error(f"Error parsing Borg config at {config_path}: {e}")
            return {
                "mode": "error",
                "requires_keyfile": False,
                "preview": f"Error reading config: {str(e)}"
            }

    async def initialize_repository(self, repository: Repository) -> Dict[str, any]:
        """Initialize a new Borg repository"""
        logger.info(f"Initializing Borg repository at {repository.path}")
        
        try:
            command, env = build_secure_borg_command(
                base_command="borg init",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--encryption=repokey"]
            )
        except Exception as e:
            logger.error(f"Failed to build secure command: {e}")
            return {"success": False, "message": f"Security validation failed: {str(e)}"}
        
        try:
            job_id = await borg_job_manager.start_borg_command(command, env=env)
            
            # Wait for initialization to complete (it's usually quick)
            max_wait = 60  # 60 seconds max
            wait_time = 0
            
            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)
                if not status:
                    return {"success": False, "message": "Job not found"}
                
                if status['completed']:
                    if status['return_code'] == 0:
                        return {"success": True, "message": "Repository initialized successfully"}
                    else:
                        # Get error output
                        output = await borg_job_manager.get_job_output_stream(job_id)
                        error_lines = [line['text'] for line in output.get('lines', [])]
                        error_text = '\n'.join(error_lines[-10:])  # Last 10 lines
                        
                        # Check if it's just because repo already exists
                        if "already exists" in error_text.lower():
                            logger.info("Repository already exists, which is fine")
                            return {"success": True, "message": "Repository already exists"}
                        
                        return {"success": False, "message": f"Initialization failed: {error_text}"}
                
                await asyncio.sleep(1)
                wait_time += 1
            
            return {"success": False, "message": "Initialization timed out"}
            
        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            return {"success": False, "message": str(e)}

    async def create_backup(self, repository: Repository, source_path: str, compression: str = "zstd", dry_run: bool = False) -> str:
        """Create a backup and return job_id for tracking"""
        logger.info(f"Creating backup for repository: {repository.name} at {repository.path}")
        
        try:
            validate_compression(compression)
            archive_name = f"backup-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            validate_archive_name(archive_name)
        except Exception as e:
            raise Exception(f"Validation failed: {str(e)}")
        
        # Build additional arguments
        additional_args = []
        
        if dry_run:
            additional_args.append("--dry-run")
        
        additional_args.extend([
            "--compression", compression,
            "--stats",
            "--progress",
            "--json",  # Enable JSON output for progress parsing
            f"{repository.path}::{archive_name}",
            source_path
        ])
        
        try:
            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path="",  # Path is included in additional_args
                passphrase=repository.get_passphrase(),
                additional_args=additional_args
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")
        
        try:
            job_id = await borg_job_manager.start_borg_command(command, env=env, is_backup=True)
            
            # Create job record in database
            db = next(get_db())
            try:
                job = Job(
                    repository_id=repository.id,
                    job_uuid=job_id,  # Store the JobManager UUID
                    type="backup",
                    status="queued",  # Will be updated to 'running' when started
                    started_at=datetime.now()
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                logger.info(f"Created job record {job.id} for backup job {job_id}")
            except Exception as e:
                logger.error(f"Failed to create job record: {e}")
            finally:
                db.close()
            
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to start backup: {e}")
            raise Exception(f"Failed to start backup: {str(e)}")

    async def list_archives(self, repository: Repository) -> List[Dict[str, any]]:
        """List all archives in a repository"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"]
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")
        
        try:
            # Create database job record for tracking
            db = next(get_db())
            try:
                job_id = await borg_job_manager.start_borg_command(command, env=env)
                
                # Create database job record
                db_job = Job(
                    repository_id=repository.id,
                    job_uuid=job_id,
                    type="list",
                    status="running",
                    started_at=datetime.utcnow()
                )
                db.add(db_job)
                db.commit()
                logger.info(f"Created database record for list archives job {job_id}")
            finally:
                db.close()
            
            # Wait for completion (list is usually quick)
            max_wait = 30  # 30 seconds max
            wait_time = 0
            
            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)
                if not status:
                    raise Exception("Job not found")
                
                if status['completed'] or status['status'] in ['completed', 'failed']:
                    # Get the output first
                    output = await borg_job_manager.get_job_output_stream(job_id)
                    
                    if status['return_code'] == 0:
                        # Parse JSON output - look for complete JSON structure
                        json_lines = []
                        for line in output.get('lines', []):
                            line_text = line['text'].strip()
                            if line_text:
                                json_lines.append(line_text)
                        
                        # Try to parse the complete JSON output
                        full_json = '\n'.join(json_lines)
                        try:
                            data = json.loads(full_json)
                            if "archives" in data:
                                logger.info(f"Successfully parsed {len(data['archives'])} archives from repository")
                                return data["archives"]
                        except json.JSONDecodeError as je:
                            logger.error(f"JSON decode error: {je}")
                            logger.error(f"Raw output: {full_json[:500]}...")  # Log first 500 chars
                        
                        # Fallback: return empty list if no valid JSON found
                        logger.warning(f"No valid archives JSON found in output, returning empty list")
                        return []
                    else:
                        error_lines = [line['text'] for line in output.get('lines', [])]
                        error_text = '\n'.join(error_lines)
                        raise Exception(f"Borg list failed with return code {status['return_code']}: {error_text}")
                    
                    break  # Exit the while loop since job is complete
                
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            raise Exception("List archives timed out")
            
        except Exception as e:
            raise Exception(f"Failed to list archives: {str(e)}")

    async def get_repo_info(self, repository: Repository) -> Dict[str, any]:
        """Get repository information"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"]
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")
        
        try:
            job_id = await borg_job_manager.start_borg_command(command, env=env)
            
            # Wait for completion
            max_wait = 30
            wait_time = 0
            
            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)
                if not status:
                    raise Exception("Job not found")
                
                if status['completed']:
                    if status['return_code'] == 0:
                        output = await borg_job_manager.get_job_output_stream(job_id)
                        
                        # Parse JSON output
                        for line in output.get('lines', []):
                            line_text = line['text']
                            if line_text.startswith('{'):
                                try:
                                    return json.loads(line_text)
                                except json.JSONDecodeError:
                                    continue
                        
                        raise Exception("No valid JSON output found")
                    else:
                        error_lines = [line['text'] for line in output.get('lines', [])]
                        error_text = '\n'.join(error_lines)
                        raise Exception(f"Borg info failed: {error_text}")
                
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            raise Exception("Get repo info timed out")
            
        except Exception as e:
            raise Exception(f"Failed to get repository info: {str(e)}")

    async def list_archive_contents(self, repository: Repository, archive_name: str) -> List[Dict[str, any]]:
        """List contents of a specific archive"""
        try:
            validate_archive_name(archive_name)
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path="",  # Path is in archive specification
                passphrase=repository.get_passphrase(),
                additional_args=["--json-lines", f"{repository.path}::{archive_name}"]
            )
        except Exception as e:
            raise Exception(f"Validation failed: {str(e)}")
        
        try:
            job_id = await borg_job_manager.start_borg_command(command, env=env)
            
            # Wait for completion
            max_wait = 60
            wait_time = 0
            
            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)
                if not status:
                    raise Exception("Job not found")
                
                if status['completed']:
                    if status['return_code'] == 0:
                        output = await borg_job_manager.get_job_output_stream(job_id)
                        
                        contents = []
                        for line in output.get('lines', []):
                            line_text = line['text']
                            if line_text.startswith('{'):
                                try:
                                    item = json.loads(line_text)
                                    contents.append(item)
                                except json.JSONDecodeError:
                                    continue
                        
                        return contents
                    else:
                        error_lines = [line['text'] for line in output.get('lines', [])]
                        error_text = '\n'.join(error_lines)
                        raise Exception(f"Borg list failed: {error_text}")
                
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            raise Exception("List archive contents timed out")
            
        except Exception as e:
            raise Exception(f"Failed to list archive contents: {str(e)}")

    async def start_repository_scan(self, scan_path: str = "/repos") -> str:
        """Start repository scan and return job_id for tracking"""
        logger.info(f"Starting repository scan in {scan_path}")
        
        try:
            safe_scan_path = sanitize_path(scan_path)
        except Exception as e:
            logger.error(f"Invalid scan path: {e}")
            raise Exception(f"Invalid scan path: {e}")
        
        # Use find command to scan for Borg repositories
        command = [
            'find', safe_scan_path, '-name', 'config', '-type', 'f',
            '-exec', 'sh', '-c',
            'if grep -q "\\[repository\\]" "$1" 2>/dev/null; then dirname "$1"; fi',
            '_', '{}', ';'
        ]
        
        try:
            job_id = await borg_job_manager.start_borg_command(command, env={})
            logger.info(f"Repository scan job {job_id} started")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to start repository scan: {e}")
            raise Exception(f"Failed to start repository scan: {e}")
    
    async def check_scan_status(self, job_id: str) -> Dict[str, any]:
        """Check status of repository scan job"""
        status = borg_job_manager.get_job_status(job_id)
        if not status:
            return {"running": False, "completed": False, "error": "Job not found"}
        
        # Get job output for error debugging
        output = ""
        try:
            job_output = await borg_job_manager.get_job_output_stream(job_id)
            if 'lines' in job_output:
                output = "\n".join([line['text'] for line in job_output['lines'][-20:]])  # Last 20 lines
        except Exception as e:
            logger.debug(f"Could not get job output for {job_id}: {e}")
        
        return {
            "running": status['running'],
            "completed": status['completed'],
            "status": status['status'],
            "started_at": status['started_at'],
            "completed_at": status['completed_at'],
            "return_code": status['return_code'],
            "error": status['error'],
            "output": output if output else None
        }
    
    async def get_scan_results(self, job_id: str) -> List[Dict]:
        """Get results of completed repository scan"""
        try:
            status = borg_job_manager.get_job_status(job_id)
            if not status or not status['completed']:
                return []
            
            if status['return_code'] != 0:
                logger.error(f"Scan job {job_id} failed with return code {status['return_code']}")
                return []
            
            # Get the output
            output = await borg_job_manager.get_job_output_stream(job_id)
            
            repo_paths = []
            for line in output.get('lines', []):
                line_text = line['text'].strip()
                if (line_text and 
                    line_text.startswith('/') and  # Must be an absolute path
                    os.path.isdir(line_text)):  # Must be a valid directory
                    
                    # Parse the Borg config file to get encryption info
                    encryption_info = self._parse_borg_config(line_text)
                    
                    repo_paths.append({
                        "path": line_text,
                        "id": f"repo_{hash(line_text)}",
                        "encryption_mode": encryption_info["mode"],
                        "requires_keyfile": encryption_info["requires_keyfile"],
                        "detected": True,
                        "config_preview": encryption_info["preview"]
                    })
            
            # Clean up job after getting results
            borg_job_manager.cleanup_job(job_id)
            
            return repo_paths
            
        except Exception as e:
            logger.error(f"Error getting scan results: {e}")
            return []

    async def verify_repository_access(self, repo_path: str, passphrase: str, keyfile_path: str = None) -> bool:
        """Verify we can access a repository with given credentials"""
        try:
            # Build environment overrides for keyfile if needed
            env_overrides = {}
            if keyfile_path:
                env_overrides['BORG_KEY_FILE'] = keyfile_path
            
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repo_path,
                passphrase=passphrase,
                additional_args=["--json"],
                environment_overrides=env_overrides
            )
        except Exception as e:
            logger.error(f"Security validation failed: {e}")
            return False
        
        try:
            job_id = await borg_job_manager.start_borg_command(command, env=env)
            
            # Wait for completion
            max_wait = 30
            wait_time = 0
            
            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)
                
                if not status:
                    return False
                
                if status['completed'] or status['status'] == 'failed':
                    success = status['return_code'] == 0
                    # Clean up job
                    borg_job_manager.cleanup_job(job_id)
                    return success
                
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to verify repository access: {e}")
            return False

    # Legacy method for compatibility - calls the new async scan
    async def scan_for_repositories(self, scan_path: str = "/repos") -> List[Dict]:
        """Legacy method - use start_repository_scan + check_scan_status + get_scan_results instead"""
        job_id = await self.start_repository_scan(scan_path)
        
        # Wait for completion
        max_wait = 60
        wait_time = 0
        
        while wait_time < max_wait:
            status = await self.check_scan_status(job_id)
            if status['completed']:
                return await self.get_scan_results(job_id)
            
            await asyncio.sleep(1)
            wait_time += 1
        
        logger.error(f"Legacy scan timed out for job {job_id}")
        return []


borg_service = BorgService()