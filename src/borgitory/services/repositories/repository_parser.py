"""
RepositoryParser - Handles Borg repository discovery and parsing
"""

import asyncio
import configparser
import json
import logging
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from borgitory.models.database import Repository
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.jobs.job_manager import JobManager
from borgitory.utils.security import build_secure_borg_command

logger = logging.getLogger(__name__)


class RepositoryParser:
    """
    Handles Borg repository discovery, parsing, and validation.

    Responsibilities:
    - Parse Borg repository configurations
    - Scan filesystem for Borg repositories
    - Verify repository access and validity
    - Extract repository metadata
    """

    def __init__(
        self,
        command_runner: Optional[SimpleCommandRunner] = None,
        job_manager: Optional[JobManager] = None,
    ) -> None:
        self.command_runner = command_runner or SimpleCommandRunner()
        self.job_manager = job_manager

    def parse_borg_config(self, repo_path: str) -> Dict[str, Any]:
        """Parse a Borg repository config file to determine encryption mode"""
        config_path = os.path.join(repo_path, "config")

        try:
            if not os.path.exists(config_path):
                return {
                    "mode": "unknown",
                    "requires_keyfile": False,
                    "preview": "Config file not found",
                }

            with open(config_path, "r", encoding="utf-8") as f:
                config_content = f.read()

            # Parse the config file (it's an INI-like format)
            config = configparser.ConfigParser()
            config.read_string(config_content)

            # Debug: log the actual config content to understand structure
            logger.info(f"Parsing Borg config at {config_path}")
            logger.info(f"Sections found: {config.sections()}")

            # Check if this looks like a Borg repository
            if not config.has_section("repository"):
                return {
                    "mode": "invalid",
                    "requires_keyfile": False,
                    "preview": "Not a valid Borg repository (no [repository] section)",
                }

            # Log all options in repository section
            if config.has_section("repository"):
                repo_options = dict(config.items("repository"))
                logger.info(f"Repository section options: {repo_options}")

            # The key insight: Borg stores encryption info differently
            # Check for a key file in the repository directory
            security_dir = os.path.join(repo_path, "security")
            key_type_file = os.path.join(repo_path, "key-type")

            has_security_dir = os.path.exists(security_dir)
            has_key_type_file = os.path.exists(key_type_file)

            logger.info(f"Security directory exists: {has_security_dir}")
            logger.info(f"Key-type file exists: {has_key_type_file}")

            # Try to determine encryption mode from various indicators
            mode = "unknown"
            requires_keyfile = False
            preview_parts = []

            if has_key_type_file:
                try:
                    with open(key_type_file, "r", encoding="utf-8") as f:
                        key_type = f.read().strip()
                        logger.info(f"Key type: {key_type}")
                        preview_parts.append(f"Key type: {key_type}")

                        if key_type in [
                            "blake2-chacha20-poly1305",
                            "argon2-chacha20-poly1305",
                        ]:
                            mode = "encrypted"
                            requires_keyfile = False  # Passphrase mode
                        elif key_type in [
                            "blake2-aes256-ctr-hmac-sha256",
                            "argon2-aes256-ctr-hmac-sha256",
                        ]:
                            mode = "encrypted"
                            requires_keyfile = True  # Key file mode
                        else:
                            mode = "encrypted"
                            requires_keyfile = False  # Assume passphrase by default
                except Exception as e:
                    logger.warning(f"Could not read key-type file: {e}")
                    preview_parts.append(f"Could not read key-type: {e}")

            if has_security_dir:
                try:
                    security_files = os.listdir(security_dir)
                    logger.info(f"Security directory contents: {security_files}")
                    preview_parts.append(f"Security files: {len(security_files)} files")

                    if not mode or mode == "unknown":
                        if security_files:
                            mode = "encrypted"
                            requires_keyfile = (
                                False  # Security dir usually means passphrase
                            )
                        else:
                            mode = "unencrypted"
                            requires_keyfile = False
                except Exception as e:
                    logger.warning(f"Could not read security directory: {e}")
                    preview_parts.append(f"Security directory error: {e}")

            # If we still don't know, make an educated guess
            if mode == "unknown":
                if has_security_dir or has_key_type_file:
                    mode = "encrypted"
                    requires_keyfile = False
                else:
                    mode = "unencrypted"
                    requires_keyfile = False

            # Get some repository info if available
            if config.has_section("repository"):
                try:
                    repo_section = config["repository"]
                    if "version" in repo_section:
                        preview_parts.append(f"Version: {repo_section['version']}")
                    if "segments_per_dir" in repo_section:
                        preview_parts.append(
                            f"Segments per dir: {repo_section['segments_per_dir']}"
                        )
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

    async def start_repository_scan(self, scan_path: str = "/mnt") -> str:
        """Start an asynchronous repository scan and return job_id for tracking"""

        logger.info(f"Starting repository scan in {scan_path}")

        # Use the job manager to track the scan job
        if not self.job_manager:
            raise RuntimeError(
                "JobManager not provided - must be injected via dependency injection"
            )
        job_manager = self.job_manager

        # Create a find command to look for Borg repositories
        # Look for directories containing 'config' and 'data' subdirectories (typical Borg structure)
        command = [
            "find",
            scan_path,
            "-type",
            "d",
            "-name",
            "config",
            "-execdir",
            "test",
            "-d",
            "data",
            ";",
            "-printf",
            "%h\\n",
        ]

        # Alternative: Look for the specific Borg repository marker files
        # This is more accurate but might be slower
        # command = [
        #     "find",
        #     scan_path,
        #     "(",
        #     "-name", "README",
        #     "-exec", "grep", "-l", "This is a Borg Backup repository", "{}", ";",
        #     ")",
        #     "-o",
        #     "(",
        #     "-name", "config",
        #     "-exec", "grep", "-l", "\\[repository\\]", "{}", ";",
        #     ")",
        #     "|",
        #     "xargs", "dirname"
        # ]

        try:
            job_id = await job_manager.start_borg_command(command)
            logger.info(f"Started repository scan job {job_id}")
            return job_id
        except Exception as e:
            logger.error(f"Failed to start repository scan: {e}")
            raise

    async def check_scan_status(self, job_id: str) -> Dict[str, Any]:
        """Check the status of a running repository scan"""
        try:
            if not self.job_manager:
                raise RuntimeError(
                    "JobManager not provided - must be injected via dependency injection"
                )
            job_manager = self.job_manager
            status = job_manager.get_job_status(job_id)

            if not status:
                return {
                    "exists": False,
                    "completed": False,
                    "status": "not_found",
                    "error": "Job not found",
                }

            return {
                "exists": True,
                "completed": status.get("completed", False),
                "status": status.get("status", "unknown"),
                "output": status.get("output", ""),
                "error": status.get("error"),
            }
        except Exception as e:
            logger.error(f"Error checking scan status for job {job_id}: {e}")
            return {
                "exists": False,
                "completed": False,
                "status": "error",
                "error": str(e),
            }

    async def get_scan_results(self, job_id: str) -> List[Dict]:
        """Get the results of a completed repository scan"""
        try:
            if not self.job_manager:
                raise RuntimeError(
                    "JobManager not provided - must be injected via dependency injection"
                )
            job_manager = self.job_manager
            job_status = job_manager.get_job_status(job_id)

            if not job_status or not job_status.get("completed"):
                logger.warning(f"Job {job_id} is not completed yet")
                return []

            output = job_status.get("output", "")
            if job_status.get("error"):
                logger.error(f"Scan job {job_id} had errors: {job_status['error']}")

            return await self._parse_scan_output(output)
        except Exception as e:
            logger.error(f"Error getting scan results for job {job_id}: {e}")
            return []

    async def _parse_scan_output(self, output: str) -> List[Dict]:
        """Parse the output from find command to identify potential Borg repositories"""
        repositories = []

        if not output.strip():
            logger.warning("Scan output is empty")
            return repositories

        # Process each line as a potential repository path
        for line in output.strip().split("\n"):
            repo_path = line.strip()
            if not repo_path or not os.path.exists(repo_path):
                continue

            logger.info(f"Examining potential repository at: {repo_path}")

            # Parse the repository config to get more info
            config_info = self.parse_borg_config(repo_path)

            # Skip if it's not a valid Borg repository
            if config_info["mode"] in ["invalid", "error"]:
                logger.debug(f"Skipping {repo_path}: {config_info['preview']}")
                continue

            # Try to get repository name from path
            repo_name = os.path.basename(repo_path)
            if not repo_name:
                repo_name = "unnamed_repository"

            repository_info = {
                "path": repo_path,
                "name": repo_name,
                "encryption_mode": config_info["mode"],
                "requires_keyfile": config_info["requires_keyfile"],
                "preview": config_info["preview"],
                "size": "Unknown",
                "last_backup": None,
            }

            # Try to get additional repository info if accessible
            try:
                # Check if we can get basic repository info
                # This might fail if repository requires authentication
                additional_info = await self._get_repository_metadata(repo_path)
                repository_info.update(additional_info)
            except Exception as e:
                logger.debug(f"Could not get metadata for {repo_path}: {e}")
                repository_info["preview"] += f"; Metadata unavailable: {str(e)}"

            repositories.append(repository_info)
            logger.info(f"Found repository: {repo_name} at {repo_path}")

        logger.info(f"Found {len(repositories)} repositories total")
        return repositories

    async def _get_repository_metadata(self, repo_path: str) -> Dict[str, Any]:
        """Try to get additional metadata about a repository (size, last backup, etc.)"""
        metadata = {}

        try:
            # Try to get repository size
            if os.path.exists(repo_path):
                # Use du to get directory size
                result = await self.command_runner.run_command(
                    ["du", "-sh", repo_path],
                    timeout=10,  # Quick timeout
                )
                if result.return_code == 0:
                    size_line = result.stdout.strip().split("\t")[0]
                    metadata["size"] = size_line
        except Exception as e:
            logger.debug(f"Could not get size for {repo_path}: {e}")

        # Try to determine last backup time from directory timestamps
        try:
            data_dir = os.path.join(repo_path, "data")
            if os.path.exists(data_dir):
                # Get the most recent modification time in the data directory
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

    async def verify_repository_access(
        self, repository: Repository, test_passphrase: str = ""
    ) -> Dict[str, Any]:
        """Verify that we can access a repository with given credentials"""
        try:
            # Use the provided passphrase or the one stored in the repository
            passphrase = (
                test_passphrase
                if test_passphrase is not None
                else repository.get_passphrase()
            )

            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=passphrase,
                additional_args=["--json"],
            )
        except Exception as e:
            return {
                "accessible": False,
                "error": f"Security validation failed: {str(e)}",
                "requires_passphrase": True,
            }

        try:
            # Start the borg info command to test access
            if not self.job_manager:
                raise RuntimeError(
                    "JobManager not provided - must be injected via dependency injection"
                )
            job_manager = self.job_manager
            job_id = await job_manager.start_borg_command(command, env=env)

            # Wait for completion with a reasonable timeout
            max_wait = 15  # 15 seconds should be enough for info command
            wait_time = 0

            while wait_time < max_wait:
                status = job_manager.get_job_status(job_id)
                if not status:
                    return {
                        "accessible": False,
                        "error": "Verification job not found",
                        "requires_passphrase": True,
                    }

                if status["completed"] or status["status"] in ["completed", "failed"]:
                    if status.get("error"):
                        error_msg = status["error"]

                        # Check for common error patterns
                        if (
                            "PassphraseWrong" in error_msg
                            or "passphrase" in error_msg.lower()
                        ):
                            return {
                                "accessible": False,
                                "error": "Incorrect passphrase",
                                "requires_passphrase": True,
                            }
                        elif "does not exist" in error_msg:
                            return {
                                "accessible": False,
                                "error": "Repository does not exist or is not a Borg repository",
                                "requires_passphrase": False,
                            }
                        else:
                            return {
                                "accessible": False,
                                "error": f"Repository access failed: {error_msg}",
                                "requires_passphrase": True,
                            }
                    else:
                        # Success case
                        output = status.get("output", "")
                        repo_info = {}

                        try:
                            if output.strip():
                                repo_info = json.loads(output)
                        except json.JSONDecodeError:
                            # Output might not be JSON, that's okay
                            pass

                        return {
                            "accessible": True,
                            "error": None,
                            "requires_passphrase": False,
                            "repository_info": repo_info,
                        }

                await asyncio.sleep(0.5)
                wait_time += 0.5

            # Timeout case
            return {
                "accessible": False,
                "error": "Repository verification timed out",
                "requires_passphrase": True,
            }

        except Exception as e:
            logger.error(f"Error verifying repository access: {e}")
            return {
                "accessible": False,
                "error": f"Verification error: {str(e)}",
                "requires_passphrase": True,
            }

    async def scan_for_repositories(self, scan_path: str = "/mnt") -> List[Dict]:
        """Legacy method - use start_repository_scan + check_scan_status + get_scan_results instead"""
        job_id = await self.start_repository_scan(scan_path)

        max_wait = 300
        wait_time = 0

        logger.info(f"Waiting for scan completion (max {max_wait}s)...")
        while wait_time < max_wait:
            status = await self.check_scan_status(job_id)

            if wait_time % 10 == 0:
                logger.info(
                    f"Scan progress: {wait_time}s elapsed, status: {status.get('status', 'unknown')}"
                )
                if status.get("output"):
                    logger.debug(
                        f"Current output: {status['output'][-200:]}"
                    )  # Last 200 chars

            if status.get("completed"):
                logger.info(f"Scan completed after {wait_time}s")
                return await self.get_scan_results(job_id)

            if status.get("error"):
                logger.error(f"Scan error: {status['error']}")
                break

            await asyncio.sleep(1)
            wait_time += 1

        final_status = await self.check_scan_status(job_id)
        logger.error(f"Legacy scan timed out for job {job_id} after {max_wait}s")
        logger.error(f"Final status: {final_status.get('status', 'unknown')}")
        if final_status.get("output"):
            logger.error(
                f"Final output: {final_status['output'][-500:]}"
            )  # Last 500 chars
        if final_status.get("error"):
            logger.error(f"Job error: {final_status['error']}")

        raise Exception(f"Repository scan timed out after {max_wait} seconds")
