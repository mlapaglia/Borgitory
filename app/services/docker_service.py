import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Optional
import docker
from docker.models.containers import Container

from app.config import BORG_DOCKER_IMAGE

logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        self.client = docker.from_env()
        
    async def run_borg_container(
        self,
        command: list,
        environment: Dict[str, str],
        volumes: Dict[str, Dict[str, str]] = None,
        name: Optional[str] = None
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
            
            volumes["/c/code/Borgitory/borg-repos"] = {"bind": "/repos", "mode": "rw"}
            
            volumes["/c/code/Borgitory/backup-sources"] = {"bind": "/data", "mode": "ro"}
            
            env_list = [f"{k}={v}" for k, v in environment.items()]
            logger.info(f"Environment as list: {env_list}")
            
            container = self.client.containers.run(
                BORG_DOCKER_IMAGE,
                command,
                environment=env_list,
                volumes=volumes,
                detach=True,
                name=name,
                remove=True,
                network_mode='none'  # Security: no network access for Borg
            )
            
            logger.info(f"Started container {container.id} with command: {' '.join(command)}")
            return container
            
        except Exception as e:
            logger.error(f"Failed to run Borg container: {e}")
            raise
    
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