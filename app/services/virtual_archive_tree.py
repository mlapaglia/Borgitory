"""
Virtual Archive Tree - Efficient archive browsing with lazy loading
"""

import json
import re
import logging
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
import asyncio

from app.models.database import Repository
from app.utils.security import validate_archive_name, build_secure_borg_command
from app.services.job_manager_modular import get_job_manager

logger = logging.getLogger(__name__)

@dataclass
class VirtualNode:
    """Represents a node in the virtual file tree"""
    path: str
    name: str
    type: str  # 'd' for directory, '-' for file
    explicit: bool  # True if actually exists in archive, False if synthesized
    data: Optional[Dict] = None  # Original borg data if explicit
    children: Dict[str, 'VirtualNode'] = field(default_factory=dict)
    
    @property
    def is_directory(self):
        return self.type == 'd'

class VirtualArchiveTree:
    """Builds and manages a virtual tree from borg archive listings"""
    
    def __init__(self):
        self.root = VirtualNode(path='', name='', type='d', explicit=False)
        self._path_cache: Dict[str, VirtualNode] = {'': self.root}
        self._loaded_paths: Set[str] = set()  # Track which paths we've loaded from borg
    
    def _get_or_create_node(self, path: str) -> VirtualNode:
        """Get existing node or create virtual intermediate nodes as needed"""
        if path in self._path_cache:
            return self._path_cache[path]
        
        # Build path components
        parts = [p for p in path.split('/') if p]  # Filter out empty parts
        current = self.root
        current_path = ''
        
        for part in parts:
            if current_path:
                current_path += '/'
            current_path += part
            
            if part not in current.children:
                # Create virtual intermediate directory
                virtual_node = VirtualNode(
                    path=current_path,
                    name=part,
                    type='d',
                    explicit=False
                )
                current.children[part] = virtual_node
                self._path_cache[current_path] = virtual_node
            
            current = current.children[part]
        
        return current
    
    def add_entry(self, borg_entry: Dict):
        """Add an actual entry from borg, creating virtual parents as needed"""
        path = borg_entry.get('path', '').strip('/')
        if not path:
            return
        
        # Get or create parent nodes
        path_parts = path.split('/')
        if len(path_parts) > 1:
            parent_path = '/'.join(path_parts[:-1])
            parent = self._get_or_create_node(parent_path)
        else:
            parent = self.root
        
        # Create the actual node
        name = path_parts[-1]
        node = VirtualNode(
            path=path,
            name=name,
            type=borg_entry.get('type', '-'),
            explicit=True,
            data=borg_entry
        )
        
        # If node already exists as virtual, preserve its children but update type
        if name in parent.children and parent.children[name].type == 'd':
            node.children = parent.children[name].children
            if node.type == 'd':
                # Update virtual directory to be explicit
                parent.children[name].explicit = True
                parent.children[name].data = borg_entry
                self._path_cache[path] = parent.children[name]
                return
        
        parent.children[name] = node
        self._path_cache[path] = node
    
    def get_directory_contents(self, path: str) -> List[Dict]:
        """Get contents of a directory (both virtual and explicit entries)"""
        path = path.strip().strip('/')
        
        node = self._path_cache.get(path, self.root if not path else None)
        if not node or not node.is_directory:
            return []
        
        results = []
        for child in node.children.values():
            if child.explicit and child.data:
                # Use original borg data for explicit entries, but add UI-friendly fields
                entry = child.data.copy()
                entry['is_directory'] = child.is_directory
                entry['name'] = child.name  # Ensure name is available
                # Map borg fields to expected template fields
                entry['modified'] = entry.get('mtime')  # Template expects 'modified'
                results.append(entry)
            else:
                # Synthesize data for virtual directories
                results.append({
                    'path': child.path,
                    'name': child.name,
                    'type': 'd',
                    'mode': 'drwxr-xr-x',
                    'size': None,
                    'modified': None,
                    'is_directory': True,
                    'virtual': True  # Mark as synthetic
                })
        
        # Sort results: directories first, then files, both alphabetically
        results.sort(key=lambda x: (not x.get('is_directory', False), x['name'].lower()))
        
        return results
    
    def path_needs_loading(self, path: str) -> bool:
        """Check if we need to load data for this path from borg"""
        return path not in self._loaded_paths
    
    def mark_path_loaded(self, path: str):
        """Mark a path as having been loaded from borg"""
        self._loaded_paths.add(path)

class ArchiveExplorer:
    """Main class for exploring borg archives with virtual tree support"""
    
    def __init__(self):
        self.tree_cache: Dict[str, VirtualArchiveTree] = {}  # Cache per archive
    
    async def list_archive_directory_contents(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[Dict[str, any]]:
        """List contents of a specific directory within an archive"""
        try:
            validate_archive_name(archive_name)
            path = path.strip().strip("/")
            
            # Get or create tree for this archive
            cache_key = f"{repository.path}::{archive_name}"
            if cache_key not in self.tree_cache:
                self.tree_cache[cache_key] = VirtualArchiveTree()
            
            tree = self.tree_cache[cache_key]
            
            # Load data if needed
            if tree.path_needs_loading(path):
                if not path:  # Root level
                    await self._load_root_level(repository, archive_name, tree)
                else:  # Specific directory
                    await self._load_directory_children(repository, archive_name, path, tree)
                tree.mark_path_loaded(path)
            
            # Return the directory contents (mix of virtual and real)
            contents = tree.get_directory_contents(path)
            
            logger.info(f"Returning {len(contents)} items for path '{path}' in archive {archive_name}")
            
            return contents
            
        except Exception as e:
            logger.error(f"Failed to list directory contents for {path} in {archive_name}: {e}")
            raise Exception(f"Failed to list directory contents: {str(e)}")
    
    async def _load_root_level(
        self, repository: Repository, archive_name: str, tree: VirtualArchiveTree
    ):
        """Load root level entries and build initial tree structure"""
        logger.info(f"Loading root level structure for archive {archive_name}")
        
        # Get all entries to build complete tree structure
        # This is needed to understand the full hierarchy
        borg_args = [
            "--json-lines",
            f"{repository.path}::{archive_name}"
        ]
        
        entries = await self._run_borg_list(repository, borg_args)
        
        # Build the virtual tree from all entries
        root_items = set()
        for entry in entries:
            path = entry.get('path', '').strip('/')
            if path:
                # Add to tree (this creates virtual parents)
                tree.add_entry(entry)
                # Track root level items
                root_part = path.split('/')[0]
                if root_part:
                    root_items.add(root_part)
        
        logger.info(f"Built tree structure with {len(entries)} total entries, {len(root_items)} root items")
        
    async def _load_directory_children(
        self, repository: Repository, archive_name: str, path: str, tree: VirtualArchiveTree
    ):
        """Load children of a specific directory"""
        logger.info(f"Loading children for path: {path}")
        
        # Check if we have this directory in our tree already from root loading
        # If so, we might already have all the data we need
        node = tree._path_cache.get(path)
        if node and node.children:
            logger.info(f"Directory {path} already has {len(node.children)} children in tree")
            return
        
        # Use pattern to get immediate children only
        escaped_path = re.escape(path)
        borg_args = [
            "--json-lines",
            "--pattern", f"+ re:^{escaped_path}/[^/]+/?$",
            "--pattern", "- *",
            f"{repository.path}::{archive_name}"
        ]
        
        entries = await self._run_borg_list(repository, borg_args)
        
        # Add all entries to tree
        for entry in entries:
            tree.add_entry(entry)
        
        logger.info(f"Loaded {len(entries)} direct children for {path}")
    
    async def _run_borg_list(
        self, repository: Repository, borg_args: List[str], limit: Optional[int] = None
    ) -> List[Dict]:
        """Run borg list command and parse results"""
        command, env = build_secure_borg_command(
            base_command="borg list",
            repository_path="",
            passphrase=repository.get_passphrase(),
            additional_args=borg_args,
        )
        
        logger.debug(f"Running borg command: {' '.join(command[:3])}...")  # Don't log full command for security
        
        job_manager = get_job_manager()
        job_id = await job_manager.start_borg_command(command, env=env)
        
        # Wait for completion
        max_wait = 120  # Longer timeout for large archives
        wait_time = 0
        
        while wait_time < max_wait:
            status = job_manager.get_job_status(job_id)
            if not status:
                raise Exception("Job not found")
            
            if status["completed"]:
                if status["return_code"] == 0:
                    output = await job_manager.get_job_output_stream(job_id)
                    
                    entries = []
                    count = 0
                    for line in output.get("lines", []):
                        if limit and count >= limit:
                            break
                        
                        line_text = line["text"]
                        if line_text.startswith("{"):
                            try:
                                item = json.loads(line_text)
                                entries.append(item)
                                count += 1
                            except json.JSONDecodeError:
                                continue
                    
                    logger.debug(f"Parsed {len(entries)} entries from borg output")
                    return entries
                else:
                    error_lines = [line["text"] for line in output.get("lines", [])]
                    error_text = "\n".join(error_lines)
                    raise Exception(f"Borg list failed: {error_text}")
            
            await asyncio.sleep(0.5)
            wait_time += 0.5
        
        raise Exception("List archive contents timed out")
    
    def clear_cache(self, archive_key: Optional[str] = None):
        """Clear cache for specific archive or all archives"""
        if archive_key:
            self.tree_cache.pop(archive_key, None)
        else:
            self.tree_cache.clear()