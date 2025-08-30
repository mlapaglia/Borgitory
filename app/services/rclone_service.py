import asyncio
import json
import os
import subprocess
from datetime import datetime
from typing import AsyncGenerator, Dict, Optional
from pathlib import Path

from app.models.database import Repository


class RcloneService:
    def __init__(self):
        self.rclone_config_dir = Path("./data/rclone")
        self.rclone_config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.rclone_config_dir / "rclone.conf"
    
    async def configure_s3_remote(
        self,
        remote_name: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        endpoint: Optional[str] = None
    ) -> bool:
        """Configure an S3 remote in Rclone"""
        try:
            config_content = f"""
[{remote_name}]
type = s3
provider = AWS
access_key_id = {access_key_id}
secret_access_key = {secret_access_key}
region = {region}
"""
            if endpoint:
                config_content += f"endpoint = {endpoint}\n"
            
            # Append to config file
            with open(self.config_file, "a") as f:
                f.write(config_content)
            
            return True
            
        except Exception as e:
            print(f"Failed to configure S3 remote: {e}")
            return False
    
    async def sync_repository_to_s3(
        self,
        repository: Repository,
        remote_name: str,
        bucket_name: str,
        path_prefix: str = ""
    ) -> AsyncGenerator[Dict, None]:
        """Sync a Borg repository to S3 using Rclone"""
        
        remote_path = f"{remote_name}:{bucket_name}"
        if path_prefix:
            remote_path = f"{remote_path}/{path_prefix}"
        
        command = [
            "rclone", "sync",
            repository.path,
            remote_path,
            "--config", str(self.config_file),
            "--progress",
            "--stats", "1s",
            "--verbose"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            yield {
                "type": "started",
                "command": " ".join(command),
                "pid": process.pid
            }
            
            # Read stdout and stderr concurrently
            async def read_stream(stream, stream_type):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    
                    decoded_line = line.decode('utf-8').strip()
                    progress_data = self.parse_rclone_progress(decoded_line)
                    
                    if progress_data:
                        yield {
                            "type": "progress",
                            **progress_data
                        }
                    else:
                        yield {
                            "type": "log",
                            "stream": stream_type,
                            "message": decoded_line
                        }
            
            # Stream both stdout and stderr
            async for item in self._merge_async_generators(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr")
            ):
                yield item
            
            # Wait for process to complete
            return_code = await process.wait()
            
            yield {
                "type": "completed",
                "return_code": return_code,
                "status": "success" if return_code == 0 else "failed"
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "message": str(e)
            }
    
    async def test_s3_connection(
        self,
        remote_name: str,
        bucket_name: str
    ) -> Dict:
        """Test S3 connection by listing bucket contents"""
        try:
            command = [
                "rclone", "lsd",
                f"{remote_name}:{bucket_name}",
                "--config", str(self.config_file),
                "--max-depth", "1"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return {
                    "status": "success",
                    "message": "Connection successful",
                    "output": stdout.decode('utf-8')
                }
            else:
                return {
                    "status": "failed",
                    "message": stderr.decode('utf-8')
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def parse_rclone_progress(self, line: str) -> Optional[Dict]:
        """Parse Rclone progress output"""
        # Look for progress statistics
        if "Transferred:" in line:
            try:
                # Example: "Transferred:   	  123.45 MiByte / 456.78 MiByte, 27%, 12.34 MiByte/s, ETA 1m23s"
                parts = line.split()
                if len(parts) >= 6:
                    transferred = parts[1]
                    total = parts[4].rstrip(',')
                    percentage = parts[5].rstrip('%,')
                    speed = parts[6] if len(parts) > 6 else "0"
                    
                    return {
                        "transferred": transferred,
                        "total": total,
                        "percentage": float(percentage) if percentage.replace('.', '').isdigit() else 0,
                        "speed": speed
                    }
            except (IndexError, ValueError):
                pass
        
        # Look for ETA information
        if "ETA" in line:
            try:
                eta_part = line.split("ETA")[-1].strip()
                return {
                    "eta": eta_part
                }
            except:
                pass
        
        return None
    
    async def _merge_async_generators(self, *async_generators):
        """Merge multiple async generators into one"""
        tasks = []
        for gen in async_generators:
            async def wrapper(g):
                async for item in g:
                    yield item
            tasks.append(wrapper(gen))
        
        # This is a simplified merge - in production you'd want a more sophisticated approach
        for task in tasks:
            async for item in task:
                yield item
    
    def get_configured_remotes(self) -> list:
        """Get list of configured Rclone remotes"""
        try:
            if not self.config_file.exists():
                return []
            
            with open(self.config_file, 'r') as f:
                content = f.read()
            
            remotes = []
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    remote_name = line[1:-1]
                    if remote_name:
                        remotes.append(remote_name)
            
            return remotes
            
        except Exception:
            return []


rclone_service = RcloneService()