import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Optional
import docker
from docker.models.containers import Container

from app.config import (
    BORG_DOCKER_IMAGE, 
    BORG_REPOS_HOST_PATH, 
    BACKUP_SOURCES_HOST_PATH,
    BORG_REPOS_CONTAINER_PATH,
    BACKUP_SOURCES_CONTAINER_PATH
)

logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        self.client = docker.from_env()
        
    async def run_borg_container(
        self,
        command: list,
        environment: Dict[str, str],
        volumes: Dict[str, Dict[str, str]] = None,
        name: Optional[str] = None,
        stream_logs: bool = True,
        job_id: Optional[str] = None,
        remove_on_exit: bool = True
    ) -> Container:
        """Run a Borg command in a Docker container"""
        logger.info(f"Starting Borg container with command: {' '.join(command)}")
        logger.info(f"Using Docker image: {BORG_DOCKER_IMAGE}")
        logger.info(f"Environment variables: {list(environment.keys())}")
        logger.info(f"Environment values (first 10 chars): {[(k, v[:10] + '...' if len(v) > 10 else v) for k, v in environment.items()]}")
        logger.info(f"Volumes: {volumes}")
        
        try:
            try:
                self.client.images.get(BORG_DOCKER_IMAGE)
                logger.info(f"Using existing image: {BORG_DOCKER_IMAGE}")
            except docker.errors.ImageNotFound:
                logger.info(f"Image {BORG_DOCKER_IMAGE} not found locally, pulling...")
                try:
                    self.client.images.pull(BORG_DOCKER_IMAGE)
                    logger.info(f"Successfully pulled image: {BORG_DOCKER_IMAGE}")
                except Exception as pull_error:
                    logger.error(f"Failed to pull image {BORG_DOCKER_IMAGE}: {pull_error}")
                    raise Exception(f"Could not pull required Docker image {BORG_DOCKER_IMAGE}: {pull_error}")
            except Exception as image_error:
                logger.error(f"Error checking for image {BORG_DOCKER_IMAGE}: {image_error}")
                raise Exception(f"Docker image error: {image_error}")
            
            if volumes is None:
                volumes = {}
            
            # Use configurable paths instead of hardcoded Windows paths
            volumes[BORG_REPOS_HOST_PATH] = {"bind": BORG_REPOS_CONTAINER_PATH, "mode": "rw"}
            volumes[BACKUP_SOURCES_HOST_PATH] = {"bind": BACKUP_SOURCES_CONTAINER_PATH, "mode": "ro"}
            
            # Add shared communication volume if job_id provided
            if job_id:
                import tempfile
                import os
                
                # Create temporary directory for job communication
                temp_dir = os.path.join(tempfile.gettempdir(), f"borg_job_{job_id}")
                os.makedirs(temp_dir, exist_ok=True)
                volumes[temp_dir] = {"bind": "/shared", "mode": "rw"}
                
                # Add job_id to environment for container to use
                environment["JOB_ID"] = job_id
                environment["SHARED_DIR"] = "/shared"
            
            env_list = [f"{k}={v}" for k, v in environment.items()]
            logger.info(f"Environment as list: {env_list}")
            
            container = self.client.containers.run(
                BORG_DOCKER_IMAGE,
                command,
                environment=env_list,
                volumes=volumes,
                detach=True,
                name=name,
                remove=remove_on_exit,
                network_mode='none'  # Security: no network access for Borg
            )
            
            logger.info(f"Started container {container.id} with command: {' '.join(command)}")
            
            # Start log streaming in background if requested
            if stream_logs:
                import asyncio
                asyncio.create_task(self._stream_container_logs_to_console(container))
            
            return container
            
        except Exception as e:
            logger.error(f"Failed to run Borg container: {e}")
            raise
    
    def check_job_status_from_file(self, job_id: str) -> Dict[str, any]:
        """Check job status from shared volume files"""
        import tempfile
        import os
        import json
        
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), f"borg_job_{job_id}")
            status_file = os.path.join(temp_dir, "status.json")
            result_file = os.path.join(temp_dir, "result.json")
            
            # Debug logging
            logger.info(f"Checking job status for {job_id}")
            logger.info(f"Temp dir: {temp_dir}")
            logger.info(f"Result file: {result_file}")
            logger.info(f"Result file exists: {os.path.exists(result_file)}")
            if os.path.exists(temp_dir):
                logger.info(f"Files in temp dir: {os.listdir(temp_dir)}")
            else:
                logger.info(f"Temp dir does not exist")
            
            status = {"running": True, "progress": None, "completed": False}
            
            # Check if result file exists (job completed)
            if os.path.exists(result_file):
                try:
                    with open(result_file, 'r') as f:
                        result = json.load(f)
                    status["completed"] = True
                    status["running"] = False
                    status["result"] = result
                    logger.info(f"Job {job_id} completed with result: {result}")
                except Exception as e:
                    logger.error(f"Error reading result file: {e}")
            
            # Check status file for progress updates
            elif os.path.exists(status_file):
                try:
                    with open(status_file, 'r') as f:
                        progress = json.load(f)
                    status["progress"] = progress
                except Exception as e:
                    logger.error(f"Error reading status file: {e}")
            
            return status
            
        except Exception as e:
            logger.error(f"Error checking job status: {e}")
            return {"running": False, "error": str(e)}
    
    def cleanup_job_files(self, job_id: str):
        """Clean up temporary job files"""
        import tempfile
        import os
        import shutil
        
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), f"borg_job_{job_id}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up job files for {job_id}")
        except Exception as e:
            logger.error(f"Error cleaning up job files: {e}")
    
    def cleanup_job_container(self, job_id: str):
        """Clean up container for a background job"""
        try:
            container_name = f"borg-scan-{job_id[:8]}"
            containers = self.client.containers.list(all=True, filters={"name": container_name})
            
            for container in containers:
                try:
                    if container.status != 'running':
                        container.remove()
                        logger.info(f"Cleaned up container {container.id} for job {job_id}")
                    else:
                        logger.warning(f"Container {container.id} for job {job_id} is still running, not removing")
                except Exception as e:
                    logger.error(f"Error removing container {container.id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up job container for {job_id}: {e}")
    
    async def _stream_container_logs_to_console(self, container: Container):
        """Stream container logs to parent console in real-time"""
        try:
            import asyncio
            import concurrent.futures
            
            def get_log_stream():
                return container.logs(stream=True, follow=True)
            
            loop = asyncio.get_event_loop()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                log_stream = await loop.run_in_executor(executor, get_log_stream)
                
                try:
                    for line in log_stream:
                        line_str = line.decode('utf-8').strip()
                        if line_str:
                            logger.info(f"[{container.name or container.short_id}] {line_str}")
                        await asyncio.sleep(0)  # Yield control
                except Exception as stream_error:
                    logger.error(f"Error in log stream for container {container.id}: {stream_error}")
                    
        except Exception as e:
            logger.error(f"Failed to stream logs from container {container.id}: {e}")

    async def stream_container_logs(self, container: Container) -> AsyncGenerator[str, None]:
        """Stream logs from a running container"""
        import concurrent.futures
        
        def get_log_iterator():
            return container.logs(stream=True, follow=True)
        
        try:
            loop = asyncio.get_event_loop()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                log_stream = await loop.run_in_executor(executor, get_log_iterator)
                
                for line in log_stream:
                    await asyncio.sleep(0)
                    yield line.decode('utf-8').strip()
                    
        except Exception as e:
            logger.error(f"Error streaming logs from container {container.id}: {e}")
            yield f"Error: {str(e)}"
    
    async def wait_for_container_async(self, container: Container) -> Dict[str, any]:
        """Wait for container to complete without blocking the event loop"""
        import asyncio
        import concurrent.futures
        
        try:
            loop = asyncio.get_event_loop()
            
            def wait_and_get_logs():
                """Run container.wait() and get logs in thread pool"""
                try:
                    # Wait for container to finish
                    result = container.wait()
                    exit_code = result.get('StatusCode', -1)
                    
                    # Get logs
                    try:
                        logs = container.logs().decode('utf-8')
                    except Exception as log_error:
                        logger.warning(f"Could not get logs: {log_error}")
                        logs = ""
                    
                    return {
                        "status": "completed",
                        "exit_code": exit_code,
                        "logs": logs
                    }
                except Exception as e:
                    # Container might be removed, try to get what we can
                    if "404" in str(e) or "No such container" in str(e):
                        logger.info(f"Container {container.id} was removed, assuming success")
                        return {
                            "status": "completed",
                            "exit_code": 0,
                            "logs": ""
                        }
                    else:
                        logger.error(f"Error waiting for container: {e}")
                        return {
                            "status": "error",
                            "exit_code": -1,
                            "logs": str(e)
                        }
            
            # Run the blocking operation in a thread pool
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(executor, wait_and_get_logs)
                return result
                    
        except Exception as e:
            logger.error(f"Error waiting for container {container.id}: {e}")
            return {"status": "error", "exit_code": -1, "logs": str(e)}

    def get_container_status(self, container: Container) -> Dict[str, any]:
        """Get container status and exit code"""
        try:
            container.reload()
            return {
                "status": container.status,
                "exit_code": container.attrs.get("State", {}).get("ExitCode")
            }
        except Exception as e:
            logger.error(f"Error getting container status: {e}")
            return {"status": "error", "exit_code": -1}
    
    def kill_container(self, container: Container) -> bool:
        """Kill a running container"""
        try:
            container.kill()
            logger.info(f"Killed container {container.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to kill container {container.id}: {e}")
            return False
    
    def get_running_containers(self) -> list:
        """Get all running Borg containers"""
        try:
            return self.client.containers.list(
                filters={"ancestor": BORG_DOCKER_IMAGE}
            )
        except Exception as e:
            logger.error(f"Error getting running containers: {e}")
            return []


docker_service = DockerService()