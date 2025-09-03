// Archive Directory Browser - Plain JavaScript implementation
class ArchiveDirectoryBrowser {
    constructor(containerId, repositoryId, archiveName) {
        this.container = document.getElementById(containerId);
        this.repositoryId = repositoryId;
        this.archiveName = archiveName;
        this.loadedPaths = new Set();
        this.expandedPaths = new Set();
        
        if (!this.container) {
            console.error(`Archive browser container '${containerId}' not found`);
            return;
        }
        
        this.init();
    }
    
    init() {
        // Initialize the browser UI
        this.container.innerHTML = `
            <div class="archive-browser">
                <div class="archive-header mb-4">
                    <h3 class="text-lg font-medium text-gray-900">Archive: ${this.archiveName}</h3>
                    <div class="breadcrumb-nav mt-2" id="breadcrumb-nav">
                        <span class="text-sm text-gray-500">Loading...</span>
                    </div>
                </div>
                <div class="archive-tree border rounded-lg bg-white" id="archive-tree">
                    <div class="p-4 text-center">
                        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
                        <span class="text-sm text-gray-500">Loading directory contents...</span>
                    </div>
                </div>
            </div>
        `;
        
        this.treeContainer = document.getElementById('archive-tree');
        this.breadcrumbContainer = document.getElementById('breadcrumb-nav');
        
        // Load root directory
        this.loadDirectory('');
    }
    
    async loadDirectory(path = '', targetElement = null) {
        const url = `/api/repositories/${this.repositoryId}/archives/${encodeURIComponent(this.archiveName)}/contents?path=${encodeURIComponent(path)}`;
        
        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Mark this path as loaded
            this.loadedPaths.add(path);
            
            if (targetElement) {
                // Expanding a specific directory
                this.renderDirectoryChildren(data.items, targetElement, path);
            } else {
                // Loading root or replacing entire tree
                this.renderDirectoryTree(data.items, path);
            }
            
            this.updateBreadcrumb(path);
            
        } catch (error) {
            console.error('Error loading directory:', error);
            const errorMessage = `
                <div class="p-4 text-center text-red-600">
                    <svg class="mx-auto h-12 w-12 text-red-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <p class="text-sm">Error loading directory contents</p>
                    <p class="text-xs text-gray-500 mt-1">${error.message}</p>
                </div>
            `;
            
            if (targetElement) {
                targetElement.innerHTML = errorMessage;
            } else {
                this.treeContainer.innerHTML = errorMessage;
            }
        }
    }
    
    renderDirectoryTree(items, currentPath) {
        if (items.length === 0) {
            this.treeContainer.innerHTML = `
                <div class="p-4 text-center text-gray-500">
                    <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                    </svg>
                    <p>This directory is empty</p>
                </div>
            `;
            return;
        }
        
        const treeHtml = items.map(item => this.createTreeNode(item, 0)).join('');
        this.treeContainer.innerHTML = `<div class="directory-contents">${treeHtml}</div>`;
    }
    
    renderDirectoryChildren(items, parentElement, parentPath) {
        const level = parseInt(parentElement.dataset.level || 0) + 1;
        const childrenHtml = items.map(item => this.createTreeNode(item, level)).join('');
        
        // Create children container
        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'directory-children';
        childrenContainer.innerHTML = childrenHtml;
        
        // Insert after the parent node
        parentElement.parentNode.insertBefore(childrenContainer, parentElement.nextSibling);
    }
    
    createTreeNode(item, level) {
        const indent = level * 20;
        const isDirectory = item.is_directory;
        const hasChildren = isDirectory;
        
        const icon = isDirectory 
            ? `<svg class="w-4 h-4 text-blue-500 mr-2" fill="currentColor" viewBox="0 0 20 20">
                   <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"></path>
               </svg>`
            : `<svg class="w-4 h-4 text-gray-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                   <path fill-rule="evenodd" d="M4 4a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-5L9 2H4z" clip-rule="evenodd"></path>
               </svg>`;
        
        const sizeInfo = !isDirectory && item.size !== null 
            ? `<span class="text-xs text-gray-500 ml-2">${this.formatFileSize(item.size)}</span>`
            : '';
        
        const modifiedInfo = item.modified 
            ? `<span class="text-xs text-gray-500 ml-2">${this.formatDate(item.modified)}</span>`
            : '';
            
        // Add download button for files
        const downloadButton = !isDirectory 
            ? `<button class="download-btn ml-2 p-1 text-gray-400 hover:text-blue-600 rounded"
                       title="Download file" 
                       onclick="downloadFile(event, '${this.repositoryId}', '${this.archiveName}', '${item.path}', '${item.name}')">
                 <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                   <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                 </svg>
               </button>`
            : '';
        
        const clickHandler = hasChildren ? `onclick="toggleDirectory(this)" title="Click to expand directory"` : '';
        const cursorStyle = hasChildren ? 'cursor-pointer' : 'cursor-default';
        
        return `
            <div class="tree-node flex items-center py-1 px-2 hover:bg-gray-50 ${cursorStyle}"
                 style="padding-left: ${20 + indent}px"
                 data-path="${item.path}" 
                 data-is-directory="${isDirectory}"
                 data-level="${level}"
                 ${clickHandler}>
                ${icon}
                <span class="flex-1 text-sm text-gray-900 select-none">${item.name}</span>
                ${sizeInfo}
                ${modifiedInfo}
                ${downloadButton}
            </div>
        `;
    }
    
    async toggleDirectory(treeNode) {
        const path = treeNode.dataset.path;
        const isExpanded = this.expandedPaths.has(path);
        
        if (isExpanded) {
            // Collapse directory
            this.collapseDirectory(treeNode, path);
        } else {
            // Expand directory
            await this.expandDirectory(treeNode, path);
        }
    }
    
    async expandDirectory(treeNode, path) {
        // Show loading state by replacing folder icon with spinner
        const icon = treeNode.querySelector('svg');
        const originalIcon = icon.outerHTML;
        icon.outerHTML = '<div class="w-4 h-4 mr-2 animate-spin rounded-full border-2 border-blue-600 border-t-transparent"></div>';
        
        try {
            await this.loadDirectory(path, treeNode);
            this.expandedPaths.add(path);
        } catch (error) {
            console.error('Error expanding directory:', error);
        }
        
        // Restore original folder icon
        const spinner = treeNode.querySelector('.animate-spin');
        if (spinner) {
            spinner.outerHTML = originalIcon;
        }
    }
    
    collapseDirectory(treeNode, path) {
        // Find and remove children
        const childrenContainer = treeNode.parentNode.querySelector('.directory-children');
        if (childrenContainer) {
            childrenContainer.remove();
        }
        
        this.expandedPaths.delete(path);
    }
    
    updateBreadcrumb(currentPath) {
        if (!currentPath) {
            this.breadcrumbContainer.innerHTML = `
                <span class="text-sm font-medium text-gray-900">Root Directory</span>
            `;
            return;
        }
        
        const pathParts = currentPath.split('/').filter(part => part);
        let breadcrumbHtml = `
            <button onclick="archiveBrowser.loadDirectory('')" 
                    class="text-sm text-blue-600 hover:text-blue-800 underline">
                Root
            </button>
        `;
        
        let buildPath = '';
        pathParts.forEach((part, index) => {
            buildPath += (buildPath ? '/' : '') + part;
            const isLast = index === pathParts.length - 1;
            
            if (isLast) {
                breadcrumbHtml += ` / <span class="text-sm font-medium text-gray-900">${part}</span>`;
            } else {
                breadcrumbHtml += ` / <button onclick="archiveBrowser.loadDirectory('${buildPath}')" 
                                            class="text-sm text-blue-600 hover:text-blue-800 underline">${part}</button>`;
            }
        });
        
        this.breadcrumbContainer.innerHTML = breadcrumbHtml;
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
    
    formatDate(dateString) {
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        } catch (error) {
            return dateString;
        }
    }
}

// Global functions for event handlers (since we can't use arrow functions in onclick)
let archiveBrowser = null;

function toggleDirectory(btn) {
    if (archiveBrowser) {
        archiveBrowser.toggleDirectory(btn);
    } else {
        console.error('archiveBrowser is null or undefined');
    }
}

function downloadFile(event, repositoryId, archiveName, filePath, fileName) {
    // Stop event propagation to prevent triggering directory expansion
    event.stopPropagation();
    
    // Create download URL
    const downloadUrl = `/api/repositories/${repositoryId}/archives/${encodeURIComponent(archiveName)}/extract?file=${encodeURIComponent(filePath)}`;
    
    // Create temporary link and trigger download
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showNotification(`Downloading ${fileName}...`, 'info');
}

// viewArchiveContents function moved to utils.js to avoid conflicts

function closeArchiveModal() {
    const archiveModal = document.getElementById('archive-contents-modal');
    if (archiveModal) {
        archiveModal.classList.add('hidden');
        archiveBrowser = null;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners for any existing archive view buttons
    document.addEventListener('click', function(event) {
        if (event.target.matches('[onclick*="viewArchiveContents"]')) {
            // Extract parameters from onclick attribute if needed
            // This handles dynamically created buttons
        }
    });
});