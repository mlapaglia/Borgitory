import asyncio
import json
import logging
import re
import os
from datetime import datetime, UTC
from typing import Dict, List, Optional

from app.models.database import Repository, Job, get_db
from app.services.job_manager import borg_job_manager
from app.utils.security import (
    build_secure_borg_command,
    validate_archive_name,
    validate_compression,
    sanitize_path,
)

logger = logging.getLogger(__name__)


class BorgService:
    def __init__(self):
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    def _parse_borg_config(self, repo_path: str) -> Dict[str, any]:
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
            import configparser

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
            key_files = []
            try:
                for item in os.listdir(repo_path):
                    if item.startswith("key.") or "key" in item.lower():
                        key_files.append(item)
            except (OSError, ValueError):
                pass

            # Method 1: Check for repokey data in config
            encryption_mode = "unknown"
            requires_keyfile = False
            preview = "Repository detected"

            # Look for key-related sections
            key_sections = [s for s in config.sections() if "key" in s.lower()]
            logger.info(f"Key-related sections: {key_sections}")

            # Check repository section for encryption hints
            repo_section = dict(config.items("repository"))

            # Check for encryption by looking for the 'key' field in repository section
            if "key" in repo_section:
                # Repository has a key field - this means it's encrypted
                key_value = repo_section["key"]

                if (
                    key_value and len(key_value) > 50
                ):  # Key data is present and substantial
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
                        preview = (
                            "Encrypted repository (key field present but unclear mode)"
                        )
            elif key_files:
                # No key in config but key files found - definitely keyfile mode
                encryption_mode = "keyfile"
                requires_keyfile = True
                preview = f"Encrypted repository (keyfile mode) - found key files: {', '.join(key_files)}"
            else:
                # No key field and no key files - check for other encryption indicators
                all_content_lower = config_content.lower()
                if any(
                    word in all_content_lower
                    for word in ["encrypt", "cipher", "algorithm", "blake2", "aes"]
                ):
                    encryption_mode = "encrypted"
                    requires_keyfile = False
                    preview = (
                        "Encrypted repository (encryption detected but mode unclear)"
                    )
                else:
                    # Likely unencrypted (very rare for Borg)
                    encryption_mode = "none"
                    requires_keyfile = False
                    preview = "Unencrypted repository (no encryption detected)"

            return {
                "mode": encryption_mode,
                "requires_keyfile": requires_keyfile,
                "preview": preview,
            }

        except Exception as e:
            logger.error(f"Error parsing Borg config at {config_path}: {e}")
            return {
                "mode": "error",
                "requires_keyfile": False,
                "preview": f"Error reading config: {str(e)}",
            }

    async def initialize_repository(self, repository: Repository) -> Dict[str, any]:
        """Initialize a new Borg repository"""
        logger.info(f"Initializing Borg repository at {repository.path}")

        try:
            command, env = build_secure_borg_command(
                base_command="borg init",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--encryption=repokey"],
            )
        except Exception as e:
            logger.error(f"Failed to build secure command: {e}")
            return {
                "success": False,
                "message": f"Security validation failed: {str(e)}",
            }

        try:
            job_id = await borg_job_manager.start_borg_command(command, env=env)

            # Wait for initialization to complete (it's usually quick)
            max_wait = 60  # 60 seconds max
            wait_time = 0

            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)
                if not status:
                    return {"success": False, "message": "Job not found"}

                if status["completed"]:
                    if status["return_code"] == 0:
                        return {
                            "success": True,
                            "message": "Repository initialized successfully",
                        }
                    else:
                        # Get error output
                        output = await borg_job_manager.get_job_output_stream(job_id)
                        error_lines = [line["text"] for line in output.get("lines", [])]
                        error_text = "\n".join(error_lines[-10:])  # Last 10 lines

                        # Check if it's just because repo already exists
                        if "already exists" in error_text.lower():
                            logger.info("Repository already exists, which is fine")
                            return {
                                "success": True,
                                "message": "Repository already exists",
                            }

                        return {
                            "success": False,
                            "message": f"Initialization failed: {error_text}",
                        }

                await asyncio.sleep(1)
                wait_time += 1

            return {"success": False, "message": "Initialization timed out"}

        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            return {"success": False, "message": str(e)}

    async def create_backup(
        self,
        repository: Repository,
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a backup and return job_id for tracking"""
        logger.info(
            f"Creating backup for repository: {repository.name} at {repository.path}"
        )

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

        additional_args.extend(
            [
                "--compression",
                compression,
                "--stats",
                "--progress",
                "--json",  # Enable JSON output for progress parsing
                f"{repository.path}::{archive_name}",
                source_path,
            ]
        )

        try:
            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path="",  # Path is included in additional_args
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

        try:
            job_id = await borg_job_manager.start_borg_command(
                command, env=env, is_backup=True
            )

            # Create job record in database
            db = next(get_db())
            try:
                job = Job(
                    repository_id=repository.id,
                    job_uuid=job_id,  # Store the JobManager UUID
                    type="backup",
                    status="queued",  # Will be updated to 'running' when started
                    started_at=datetime.now(),
                    cloud_sync_config_id=cloud_sync_config_id,
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
                additional_args=["--json"],
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
                    started_at=datetime.now(UTC),
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

                if status["completed"] or status["status"] in ["completed", "failed"]:
                    # Get the output first
                    output = await borg_job_manager.get_job_output_stream(job_id)

                    if status["return_code"] == 0:
                        # Parse JSON output - look for complete JSON structure
                        json_lines = []
                        for line in output.get("lines", []):
                            line_text = line["text"].strip()
                            if line_text:
                                json_lines.append(line_text)

                        # Try to parse the complete JSON output
                        full_json = "\n".join(json_lines)
                        try:
                            data = json.loads(full_json)
                            if "archives" in data:
                                logger.info(
                                    f"Successfully parsed {len(data['archives'])} archives from repository"
                                )
                                return data["archives"]
                        except json.JSONDecodeError as je:
                            logger.error(f"JSON decode error: {je}")
                            logger.error(
                                f"Raw output: {full_json[:500]}..."
                            )  # Log first 500 chars

                        # Fallback: return empty list if no valid JSON found
                        logger.warning(
                            "No valid archives JSON found in output, returning empty list"
                        )
                        return []
                    else:
                        error_lines = [line["text"] for line in output.get("lines", [])]
                        error_text = "\n".join(error_lines)
                        raise Exception(
                            f"Borg list failed with return code {status['return_code']}: {error_text}"
                        )

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
                additional_args=["--json"],
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

                if status["completed"]:
                    if status["return_code"] == 0:
                        output = await borg_job_manager.get_job_output_stream(job_id)

                        # Parse JSON output
                        for line in output.get("lines", []):
                            line_text = line["text"]
                            if line_text.startswith("{"):
                                try:
                                    return json.loads(line_text)
                                except json.JSONDecodeError:
                                    continue

                        raise Exception("No valid JSON output found")
                    else:
                        error_lines = [line["text"] for line in output.get("lines", [])]
                        error_text = "\n".join(error_lines)
                        raise Exception(f"Borg info failed: {error_text}")

                await asyncio.sleep(0.5)
                wait_time += 0.5

            raise Exception("Get repo info timed out")

        except Exception as e:
            raise Exception(f"Failed to get repository info: {str(e)}")

    async def list_archive_contents(
        self, repository: Repository, archive_name: str
    ) -> List[Dict[str, any]]:
        """List contents of a specific archive"""
        try:
            validate_archive_name(archive_name)
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path="",  # Path is in archive specification
                passphrase=repository.get_passphrase(),
                additional_args=["--json-lines", f"{repository.path}::{archive_name}"],
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

                if status["completed"]:
                    if status["return_code"] == 0:
                        output = await borg_job_manager.get_job_output_stream(job_id)

                        contents = []
                        for line in output.get("lines", []):
                            line_text = line["text"]
                            if line_text.startswith("{"):
                                try:
                                    item = json.loads(line_text)
                                    contents.append(item)
                                except json.JSONDecodeError:
                                    continue

                        return contents
                    else:
                        error_lines = [line["text"] for line in output.get("lines", [])]
                        error_text = "\n".join(error_lines)
                        raise Exception(f"Borg list failed: {error_text}")

                await asyncio.sleep(0.5)
                wait_time += 0.5

            raise Exception("List archive contents timed out")

        except Exception as e:
            raise Exception(f"Failed to list archive contents: {str(e)}")

    async def list_archive_directory_contents(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[Dict[str, any]]:
        """List contents of a specific directory within an archive, loading only what's needed"""
        try:
            validate_archive_name(archive_name)

            # Normalize path
            path = path.strip().strip("/")

            # Build borg list command with pattern filtering for efficiency
            borg_args = ["--json-lines"]

            # Use regex patterns based on working example
            if path:
                # For subdirectories like "data", show immediate children only
                # Pattern matches: path/immediate_child with optional trailing slash
                borg_args.extend(
                    [
                        "--pattern",
                        f"+ re:^{re.escape(path)}/[^/]+/?$",  # Include immediate children only
                        "--pattern",
                        "- *",  # Exclude everything else
                    ]
                )
            else:
                # For root level, match items without path separators
                borg_args.extend(
                    [
                        "--pattern",
                        "+ re:^[^/]+/?$",  # Include root-level items only
                        "--pattern",
                        "- *",  # Exclude everything else
                    ]
                )

            borg_args.append(f"{repository.path}::{archive_name}")

            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=borg_args,
            )

            logger.info(
                f"Running borg command for directory listing: {' '.join(command)}"
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

                if status["completed"]:
                    if status["return_code"] == 0:
                        output = await borg_job_manager.get_job_output_stream(job_id)

                        # Parse all entries
                        all_entries = []
                        for line in output.get("lines", []):
                            line_text = line["text"]
                            if line_text.startswith("{"):
                                try:
                                    item = json.loads(line_text)
                                    all_entries.append(item)
                                except json.JSONDecodeError:
                                    continue

                        logger.info(
                            f"Borg returned {len(all_entries)} entries for path '{path}'"
                        )

                        # Debug: Show first few actual paths to understand structure
                        if all_entries and len(all_entries) > 0:
                            sample_paths = [
                                entry.get("path", "NO_PATH")
                                for entry in all_entries[:5]
                            ]
                            logger.info(f"Sample paths from Borg: {sample_paths}")

                        # Filter entries to show only immediate children of the specified path
                        return self._filter_directory_contents(all_entries, path)
                    else:
                        error_lines = [line["text"] for line in output.get("lines", [])]
                        error_text = "\n".join(error_lines)
                        raise Exception(f"Borg list failed: {error_text}")

                await asyncio.sleep(0.5)
                wait_time += 0.5

            raise Exception("List archive contents timed out")

        except Exception as e:
            raise Exception(f"Failed to list directory contents: {str(e)}")

    def _filter_directory_contents(
        self, all_entries: List[Dict], target_path: str = ""
    ) -> List[Dict]:
        """Filter entries to show only immediate children of target_path"""
        target_path = target_path.strip().strip("/")

        logger.info(
            f"Filtering {len(all_entries)} entries for target_path: '{target_path}'"
        )

        # Group entries by their immediate parent under target_path
        children = {}

        for entry in all_entries:
            entry_path = entry.get("path", "").lstrip("/")

            logger.debug(f"Processing entry path: '{entry_path}'")

            # Determine if this entry is a direct child of target_path
            if target_path:
                # For subdirectory like "data", we want entries like:
                # "data/file.txt" -> include as "file.txt"
                # "data/subdir/file.txt" -> include as "subdir" (directory)
                if not entry_path.startswith(target_path + "/"):
                    continue

                # Remove the target path prefix
                relative_path = entry_path[len(target_path) + 1 :]

            else:
                # For root directory, we want entries like:
                # "file.txt" -> include as "file.txt"
                # "data/file.txt" -> include as "data" (directory)
                relative_path = entry_path

            if not relative_path:
                continue

            # Get the first component (immediate child)
            path_parts = relative_path.split("/")
            immediate_child = path_parts[0]

            # Build full path for this item
            full_path = (
                f"{target_path}/{immediate_child}" if target_path else immediate_child
            )

            if immediate_child not in children:
                # Determine if this is a directory or file
                # Use the actual Borg entry type - 'd' means directory
                is_directory = entry.get("type") == "d" or len(path_parts) > 1

                children[immediate_child] = {
                    "name": immediate_child,
                    "path": full_path,
                    "is_directory": is_directory,
                    "size": entry.get("size") if not is_directory else None,
                    "modified": entry.get("mtime"),
                    "mode": entry.get("mode"),
                    "user": entry.get("user"),
                    "group": entry.get("group"),
                }

                logger.debug(
                    f"Added item: {immediate_child} (is_directory: {is_directory})"
                )
            else:
                # If we already have this item and this entry suggests it's a directory, update it
                if len(path_parts) > 1:
                    children[immediate_child]["is_directory"] = True
                    children[immediate_child]["size"] = None
                elif not children[immediate_child]["is_directory"]:
                    # Update file info if this is the actual file entry
                    children[immediate_child]["size"] = entry.get("size")
                    children[immediate_child]["modified"] = entry.get("mtime")

        # Sort results: directories first, then files, both alphabetically
        result = list(children.values())
        result.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))

        logger.info(
            f"Filtered to {len(result)} items: {[item['name'] for item in result[:5]]}{'...' if len(result) > 5 else ''}"
        )

        return result

    async def extract_file_stream(
        self, repository: Repository, archive_name: str, file_path: str
    ):
        """Extract a single file from an archive and stream it to the client"""
        try:
            validate_archive_name(archive_name)

            # Sanitize the file path
            if not file_path or not isinstance(file_path, str):
                raise Exception("File path is required")

            # Build borg extract command with --stdout
            borg_args = ["--stdout", f"{repository.path}::{archive_name}", file_path]

            command, env = build_secure_borg_command(
                base_command="borg extract",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=borg_args,
            )

            logger.info(f"Extracting file {file_path} from archive {archive_name}")

            # Import required classes for streaming response
            from fastapi.responses import StreamingResponse
            import asyncio
            import os

            # Start the borg process
            process = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def generate_stream():
                """Generator function to stream the file content with automatic backpressure"""
                try:
                    while True:
                        # Read chunk from Borg process - this already yields control to event loop
                        chunk = await process.stdout.read(
                            65536
                        )  # 64KB chunks for efficiency
                        if not chunk:
                            break

                        # Yield chunk to client - FastAPI/Starlette handles backpressure automatically
                        yield chunk

                finally:
                    # Ensure process cleanup happens regardless of early client disconnect
                    if process.returncode is None:
                        # Process still running - terminate it
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()

                    # Check for errors if process completed normally
                    if process.returncode != 0:
                        stderr = await process.stderr.read()
                        error_msg = (
                            stderr.decode("utf-8") if stderr else "Unknown error"
                        )
                        logger.error(f"Borg extract process failed: {error_msg}")
                        raise Exception(f"Borg extract failed: {error_msg}")

            # Get filename for download header
            filename = os.path.basename(file_path)

            # Return streaming response
            return StreamingResponse(
                generate_stream(),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except Exception as e:
            logger.error(f"Failed to extract file {file_path}: {str(e)}")
            raise Exception(f"Failed to extract file: {str(e)}")

    async def start_repository_scan(self, scan_path: str = None) -> str:
        """Start repository scan and return job_id for tracking"""

        # If no specific path provided, scan all mounted volumes
        if scan_path is None:
            from app.services.volume_service import volume_service

            mounted_volumes = await volume_service.get_mounted_volumes()

            if not mounted_volumes:
                logger.warning("No mounted volumes found, falling back to /repos")
                scan_paths = ["/repos"]
            else:
                scan_paths = mounted_volumes

            logger.info(
                f"Starting repository scan across {len(scan_paths)} mounted volumes: {scan_paths}"
            )
        else:
            scan_paths = [scan_path]
            logger.info(f"Starting repository scan in specific path: {scan_path}")

        # Build command to scan multiple paths
        # Use find command to scan for Borg repositories - only check top-level subdirectories
        # This scans /backups/repo-1/, /backups/repo-2/ but not deeper like /backups/repo-1/sub/deep/

        # Start with base find command structure
        command_parts = ["find"]

        # Add all scan paths
        for path in scan_paths:
            try:
                safe_scan_path = sanitize_path(path)
                # Check if path exists before adding it
                import os

                if os.path.exists(safe_scan_path) and os.path.isdir(safe_scan_path):
                    command_parts.append(safe_scan_path)
            except Exception as e:
                logger.warning(f"Skipping invalid scan path {path}: {e}")
                continue

        # If no valid paths found, use /repos as fallback
        if len(command_parts) == 1:  # Only "find" command
            logger.warning("No valid scan paths found, using /repos as fallback")
            command_parts.append("/repos")

        # Add find parameters
        command_parts.extend(
            [
                "-mindepth",
                "2",  # Start looking 2 levels deep (scan_path/repo_name/config)
                "-maxdepth",
                "2",  # Don't go deeper than 2 levels
                "-name",
                "config",
                "-type",
                "f",
                "-exec",
                "sh",
                "-c",
                'if head -20 "$1" 2>/dev/null | grep -q "\\[repository\\]"; then echo "$(dirname "$1")"; fi',
                "_",
                "{}",
                ";",
            ]
        )

        command = command_parts

        try:
            logger.info(f"Executing scan command: {' '.join(command)}")
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
            if "lines" in job_output:
                output = "\n".join(
                    [line["text"] for line in job_output["lines"][-20:]]
                )  # Last 20 lines
        except Exception as e:
            logger.debug(f"Could not get job output for {job_id}: {e}")

        return {
            "running": status["running"],
            "completed": status["completed"],
            "status": status["status"],
            "started_at": status["started_at"],
            "completed_at": status["completed_at"],
            "return_code": status["return_code"],
            "error": status["error"],
            "output": output if output else None,
        }

    async def get_scan_results(self, job_id: str) -> List[Dict]:
        """Get results of completed repository scan"""
        try:
            status = borg_job_manager.get_job_status(job_id)
            if not status or not status["completed"]:
                return []

            if status["return_code"] != 0:
                logger.error(
                    f"Scan job {job_id} failed with return code {status['return_code']}"
                )
                return []

            # Get the output
            output = await borg_job_manager.get_job_output_stream(job_id)

            repo_paths = []
            for line in output.get("lines", []):
                line_text = line["text"].strip()
                if (
                    line_text
                    and line_text.startswith("/")  # Must be an absolute path
                    and os.path.isdir(line_text)
                ):  # Must be a valid directory
                    # Parse the Borg config file to get encryption info
                    encryption_info = self._parse_borg_config(line_text)

                    repo_paths.append(
                        {
                            "path": line_text,
                            "id": f"repo_{hash(line_text)}",
                            "encryption_mode": encryption_info["mode"],
                            "requires_keyfile": encryption_info["requires_keyfile"],
                            "detected": True,
                            "config_preview": encryption_info["preview"],
                        }
                    )

            # Clean up job after getting results
            borg_job_manager.cleanup_job(job_id)

            return repo_paths

        except Exception as e:
            logger.error(f"Error getting scan results: {e}")
            return []

    async def verify_repository_access(
        self, repo_path: str, passphrase: str, keyfile_path: str = None
    ) -> bool:
        """Verify we can access a repository with given credentials"""
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
            job_id = await borg_job_manager.start_borg_command(command, env=env)

            # Wait for completion
            max_wait = 30
            wait_time = 0

            while wait_time < max_wait:
                status = borg_job_manager.get_job_status(job_id)

                if not status:
                    return False

                if status["completed"] or status["status"] == "failed":
                    success = status["return_code"] == 0
                    # Clean up job
                    borg_job_manager.cleanup_job(job_id)
                    return success

                await asyncio.sleep(0.5)
                wait_time += 0.5

            return False

        except Exception as e:
            logger.error(f"Failed to verify repository access: {e}")
            return False

    async def scan_for_repositories(self, scan_path: str = None) -> List[Dict]:
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

            if status["completed"]:
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

        try:
            if final_status.get("running"):
                logger.warning(
                    f"Job {job_id} is still running after timeout - it may continue in background"
                )
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")

        return []


borg_service = BorgService()
