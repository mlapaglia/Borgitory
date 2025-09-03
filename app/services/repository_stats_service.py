import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.models.database import Repository
from app.utils.security import build_secure_borg_command

logger = logging.getLogger(__name__)


class RepositoryStatsService:
    """Service to gather repository statistics from Borg commands"""
    
    async def get_repository_statistics(self, repository: Repository, db: Session) -> Dict[str, Any]:
        """Gather comprehensive repository statistics"""
        try:
            # Get list of all archives
            archives = await self._get_archive_list(repository)
            if not archives:
                return {"error": "No archives found in repository"}
            
            # Get detailed info for each archive
            archive_stats = []
            for archive in archives:
                archive_info = await self._get_archive_info(repository, archive)
                if archive_info:
                    archive_stats.append(archive_info)
            
            if not archive_stats:
                return {"error": "Could not retrieve archive information"}
            
            # Sort archives by date
            archive_stats.sort(key=lambda x: x.get('start', ''))
            
            # Build statistics
            stats = {
                "repository_path": repository.path,
                "total_archives": len(archive_stats),
                "archive_stats": archive_stats,
                "size_over_time": self._build_size_timeline(archive_stats),
                "dedup_compression_stats": self._build_dedup_compression_stats(archive_stats),
                "summary": self._build_summary_stats(archive_stats)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting repository statistics: {str(e)}")
            return {"error": str(e)}
    
    async def _get_archive_list(self, repository: Repository) -> List[str]:
        """Get list of all archives in repository"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--short"]
            )
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                archives = [line.strip() for line in stdout.decode().strip().split('\n') if line.strip()]
                return archives
            else:
                logger.error(f"Borg list failed: {stderr.decode()}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing archives: {str(e)}")
            return []
    
    async def _get_archive_info(self, repository: Repository, archive_name: str) -> Dict[str, Any]:
        """Get detailed information for a specific archive"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=["--json", f"{repository.path}::{archive_name}"]
            )
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                info_data = json.loads(stdout.decode())
                
                # Extract relevant statistics
                archive_info = info_data.get('archives', [{}])[0]
                cache_info = info_data.get('cache', {})
                
                return {
                    "name": archive_name,
                    "start": archive_info.get('start', ''),
                    "end": archive_info.get('end', ''),
                    "duration": archive_info.get('duration', 0),
                    "original_size": archive_info.get('stats', {}).get('original_size', 0),
                    "compressed_size": archive_info.get('stats', {}).get('compressed_size', 0),
                    "deduplicated_size": archive_info.get('stats', {}).get('deduplicated_size', 0),
                    "nfiles": archive_info.get('stats', {}).get('nfiles', 0),
                    "unique_chunks": cache_info.get('stats', {}).get('unique_chunks', 0),
                    "total_chunks": cache_info.get('stats', {}).get('total_chunks', 0),
                    "unique_size": cache_info.get('stats', {}).get('unique_size', 0),
                    "total_size": cache_info.get('stats', {}).get('total_size', 0)
                }
            else:
                logger.error(f"Borg info failed for {archive_name}: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting archive info for {archive_name}: {str(e)}")
            return None
    
    def _build_size_timeline(self, archive_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build size over time data for charting"""
        timeline_data = {
            "labels": [],
            "datasets": [
                {
                    "label": "Original Size",
                    "data": [],
                    "borderColor": "rgb(59, 130, 246)",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "fill": False
                },
                {
                    "label": "Compressed Size", 
                    "data": [],
                    "borderColor": "rgb(16, 185, 129)",
                    "backgroundColor": "rgba(16, 185, 129, 0.1)",
                    "fill": False
                },
                {
                    "label": "Deduplicated Size",
                    "data": [],
                    "borderColor": "rgb(245, 101, 101)",
                    "backgroundColor": "rgba(245, 101, 101, 0.1)",
                    "fill": False
                }
            ]
        }
        
        for archive in archive_stats:
            # Use archive name or start time as label
            label = archive.get('start', archive.get('name', ''))[:10]  # First 10 chars for date
            timeline_data["labels"].append(label)
            
            # Convert bytes to MB for better readability
            timeline_data["datasets"][0]["data"].append(archive.get('original_size', 0) / (1024*1024))
            timeline_data["datasets"][1]["data"].append(archive.get('compressed_size', 0) / (1024*1024))
            timeline_data["datasets"][2]["data"].append(archive.get('deduplicated_size', 0) / (1024*1024))
        
        return timeline_data
    
    def _build_dedup_compression_stats(self, archive_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build deduplication and compression statistics"""
        dedup_data = {
            "labels": [],
            "datasets": [
                {
                    "label": "Compression Ratio %",
                    "data": [],
                    "borderColor": "rgb(139, 92, 246)",
                    "backgroundColor": "rgba(139, 92, 246, 0.1)",
                    "yAxisID": "y"
                },
                {
                    "label": "Deduplication Ratio %",
                    "data": [],
                    "borderColor": "rgb(245, 158, 11)",
                    "backgroundColor": "rgba(245, 158, 11, 0.1)",
                    "yAxisID": "y1"
                }
            ]
        }
        
        for archive in archive_stats:
            label = archive.get('start', archive.get('name', ''))[:10]
            dedup_data["labels"].append(label)
            
            # Calculate compression ratio
            original = archive.get('original_size', 0)
            compressed = archive.get('compressed_size', 0)
            compression_ratio = ((original - compressed) / original * 100) if original > 0 else 0
            
            # Calculate deduplication ratio
            deduplicated = archive.get('deduplicated_size', 0)
            dedup_ratio = ((compressed - deduplicated) / compressed * 100) if compressed > 0 else 0
            
            dedup_data["datasets"][0]["data"].append(round(compression_ratio, 2))
            dedup_data["datasets"][1]["data"].append(round(dedup_ratio, 2))
        
        return dedup_data
    
    def _build_summary_stats(self, archive_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build overall summary statistics"""
        if not archive_stats:
            return {}
        
        latest_archive = archive_stats[-1]
        total_original = sum(archive.get('original_size', 0) for archive in archive_stats)
        total_compressed = sum(archive.get('compressed_size', 0) for archive in archive_stats)
        total_deduplicated = sum(archive.get('deduplicated_size', 0) for archive in archive_stats)
        
        return {
            "total_archives": len(archive_stats),
            "latest_archive_date": latest_archive.get('start', ''),
            "total_original_size_gb": round(total_original / (1024**3), 2),
            "total_compressed_size_gb": round(total_compressed / (1024**3), 2),
            "total_deduplicated_size_gb": round(total_deduplicated / (1024**3), 2),
            "overall_compression_ratio": round(((total_original - total_compressed) / total_original * 100), 2) if total_original > 0 else 0,
            "overall_deduplication_ratio": round(((total_compressed - total_deduplicated) / total_compressed * 100), 2) if total_compressed > 0 else 0,
            "space_saved_gb": round((total_original - total_deduplicated) / (1024**3), 2),
            "average_archive_size_gb": round((total_original / len(archive_stats)) / (1024**3), 2) if archive_stats else 0
        }


repository_stats_service = RepositoryStatsService()