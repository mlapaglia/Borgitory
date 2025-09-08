"""
Job Executor Module - Handles subprocess execution and process management
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """Result of a process execution"""

    return_code: int
    stdout: bytes
    stderr: bytes
    error: Optional[str] = None


class JobExecutor:
    """Handles subprocess execution and output monitoring"""

    def __init__(self, subprocess_executor: Optional[Callable] = None):
        self.subprocess_executor = subprocess_executor or asyncio.create_subprocess_exec
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    async def start_process(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process:
        """Start a subprocess with the given command"""
        try:
            logger.info(f"Starting process: {' '.join(command[:3])}...")

            # Merge environment variables
            merged_env = os.environ.copy()
            if env:
                merged_env.update(env)

            process = await self.subprocess_executor(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
                cwd=cwd,
            )

            logger.info(f"Process started with PID: {process.pid}")
            return process

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            raise

    async def monitor_process_output(
        self,
        process: asyncio.subprocess.Process,
        output_callback: Optional[Callable[[str, Dict], None]] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> ProcessResult:
        """Monitor process output and return final result"""
        stdout_data = b""
        stderr_data = b""

        try:
            # Read output line by line
            async for line in process.stdout:
                line_text = line.decode("utf-8", errors="replace").rstrip()
                stdout_data += line

                # Parse progress information
                progress_info = self.parse_progress_line(line_text)

                # Call callbacks if provided
                if output_callback:
                    output_callback(line_text, progress_info)

                if progress_callback and progress_info:
                    progress_callback(progress_info)

            # Wait for process completion
            return_code = await process.wait()

            return ProcessResult(
                return_code=return_code, stdout=stdout_data, stderr=stderr_data
            )

        except Exception as e:
            error_msg = f"Process monitoring error: {e}"
            logger.error(error_msg)
            return ProcessResult(
                return_code=-1, stdout=stdout_data, stderr=stderr_data, error=error_msg
            )

    def parse_progress_line(self, line: str) -> Dict[str, Any]:
        """Parse Borg output line for progress information"""
        progress_info = {}

        try:
            # Check for Borg progress pattern
            match = self.progress_pattern.search(line)
            if match:
                progress_info = {
                    "original_size": int(match.group("original_size")),
                    "compressed_size": int(match.group("compressed_size")),
                    "deduplicated_size": int(match.group("deduplicated_size")),
                    "nfiles": int(match.group("nfiles")),
                    "path": match.group("path").strip(),
                    "timestamp": datetime.now().isoformat(),
                }

            # Parse other Borg status lines
            elif "Archive name:" in line:
                progress_info["archive_name"] = line.split("Archive name:")[-1].strip()
            elif "Archive fingerprint:" in line:
                progress_info["fingerprint"] = line.split("Archive fingerprint:")[
                    -1
                ].strip()
            elif "Time (start):" in line:
                progress_info["start_time"] = line.split("Time (start):")[-1].strip()
            elif "Time (end):" in line:
                progress_info["end_time"] = line.split("Time (end):")[-1].strip()

        except Exception as e:
            logger.debug(f"Error parsing progress line '{line}': {e}")

        return progress_info

    async def terminate_process(
        self, process: asyncio.subprocess.Process, timeout: float = 5.0
    ) -> bool:
        """Terminate a process gracefully, then force kill if needed"""
        try:
            if process.returncode is None:
                if hasattr(process, "terminate") and callable(process.terminate):
                    if asyncio.iscoroutinefunction(process.terminate):
                        await process.terminate()
                    else:
                        process.terminate()

                try:
                    await asyncio.wait_for(process.wait(), timeout=timeout)
                    logger.info("Process terminated gracefully")
                    return True
                except asyncio.TimeoutError:
                    logger.warning(
                        "Process did not terminate gracefully, force killing"
                    )
                    if hasattr(process, "kill") and callable(process.kill):
                        if asyncio.iscoroutinefunction(process.kill):
                            await process.kill()
                        else:
                            process.kill()
                    await process.wait()
                    logger.info("Process force killed")
                    return True
            else:
                logger.info("Process already terminated")
                return True

        except Exception as e:
            logger.error(f"Error terminating process: {e}")
            return False

    def format_command_for_logging(self, command: List[str]) -> str:
        """Format command for safe logging (hide sensitive info)"""
        safe_command = []
        skip_next = False

        for i, arg in enumerate(command):
            if skip_next:
                safe_command.append("[REDACTED]")
                skip_next = False
            elif arg in ["--encryption-passphrase", "-p", "--passphrase"]:
                safe_command.append(arg)
                skip_next = True
            elif "::" in arg and len(arg.split("::")) == 2:
                # Repository path with potential passphrase
                parts = arg.split("::")
                safe_command.append(f"{parts[0]}::[ARCHIVE]")
            else:
                safe_command.append(arg)

        return " ".join(safe_command)
