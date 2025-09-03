// Notification System
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transition-opacity duration-300 ${
        type === 'success' ? 'bg-green-100 border border-green-400 text-green-800' :
        type === 'error' ? 'bg-red-100 border border-red-400 text-red-800' :
        type === 'warning' ? 'bg-yellow-100 border border-yellow-400 text-yellow-800' :
        'bg-blue-100 border border-blue-400 text-blue-800'
    }`;
    
    notification.innerHTML = `
        <div class="flex items-center">
            <span class="mr-2">${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-2 text-current hover:bg-black hover:bg-opacity-10 rounded p-1">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                </svg>
            </button>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 300);
    }, 5000);
}

// Job History and SSE Functions
function loadJobHistory() {
    // Load job history via HTMX
    htmx.ajax('GET', '/api/jobs/html', {
        target: '#job-history',
        swap: 'innerHTML'
    });
    
    // Also load current jobs
    htmx.ajax('GET', '/api/jobs/current/html', {
        target: '#current-jobs',  
        swap: 'innerHTML'
    });
}

function initializeSSE() {
    // This would normally set up Server-Sent Events for real-time updates
    // For now, we'll use periodic refresh
    setInterval(() => {
        if (document.getElementById('current-jobs')) {
            htmx.ajax('GET', '/api/jobs/current/html', {
                target: '#current-jobs',
                swap: 'innerHTML'
            });
        }
    }, 5000);
}

// Schedule Management Functions
async function toggleSchedule(scheduleId) {
    try {
        const response = await fetch(`/api/schedules/${scheduleId}/toggle`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            showNotification(result.message, 'success');
            document.body.dispatchEvent(new CustomEvent('scheduleUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to toggle schedule: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to toggle schedule: ${error.message}`, 'error');
    }
}

async function deleteSchedule(scheduleId, scheduleName) {
    if (!confirm(`Are you sure you want to delete the schedule "${scheduleName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/schedules/${scheduleId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification(`Schedule "${scheduleName}" deleted successfully!`, 'success');
            document.body.dispatchEvent(new CustomEvent('scheduleUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to delete schedule: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to delete schedule: ${error.message}`, 'error');
    }
}

// Archive Management Functions
// Note: archiveBrowser is declared in archive-browser.js, but we reference it here
async function viewArchiveContents(repoId, archiveName) {
    // Show the archive contents modal
    const archiveModal = document.getElementById('archive-contents-modal');
    if (archiveModal) {
        archiveModal.classList.remove('hidden');
        
        // Initialize the directory browser
        archiveBrowser = new ArchiveDirectoryBrowser(
            'archive-browser-container',
            repoId,
            archiveName
        );
    } else {
        showNotification('Archive contents modal not found', 'error');
    }
}

function showArchiveContentsModal(archiveName, contents) {
    // Create modal backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
    backdrop.onclick = (e) => {
        if (e.target === backdrop) {
            document.body.removeChild(backdrop);
        }
    };
    
    // Create modal content
    const modal = document.createElement('div');
    modal.className = 'bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col';
    
    // Sort contents: directories first, then files, both alphabetically
    const sortedContents = contents.sort((a, b) => {
        const aIsDir = a.type === 'd';
        const bIsDir = b.type === 'd';
        
        if (aIsDir && !bIsDir) return -1;
        if (!aIsDir && bIsDir) return 1;
        
        return a.path.localeCompare(b.path);
    });
    
    // Format file size
    const formatSize = (size) => {
        if (!size) return '';
        const units = ['B', 'KB', 'MB', 'GB'];
        let unitIndex = 0;
        let fileSize = size;
        
        while (fileSize >= 1024 && unitIndex < units.length - 1) {
            fileSize /= 1024;
            unitIndex++;
        }
        
        return `${fileSize.toFixed(1)} ${units[unitIndex]}`;
    };
    
    // Generate contents HTML
    let contentsHtml = '';
    if (sortedContents.length === 0) {
        contentsHtml = '<div class="text-center py-8 text-gray-500">This archive is empty</div>';
    } else {
        contentsHtml = '<div class="space-y-1">';
        sortedContents.forEach(item => {
            const isDir = item.type === 'd';
            const icon = isDir ? '📁' : '📄';
            const size = isDir ? '' : formatSize(item.size);
            contentsHtml += `
                <div class="flex items-center justify-between py-2 px-3 hover:bg-gray-50 rounded text-sm">
                    <div class="flex items-center min-w-0 flex-1">
                        <span class="mr-2">${icon}</span>
                        <span class="truncate font-mono">${item.path}</span>
                    </div>
                    <div class="ml-4 text-gray-500 text-xs">${size}</div>
                </div>
            `;
        });
        contentsHtml += '</div>';
    }
    
    modal.innerHTML = `
        <div class="flex items-center justify-between p-6 border-b">
            <h3 class="text-lg font-medium">Archive Contents: ${archiveName}</h3>
            <button onclick="document.body.removeChild(this.closest('.fixed'))" class="text-gray-400 hover:text-gray-600">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
        <div class="flex-1 overflow-y-auto p-6">
            ${contentsHtml}
        </div>
        <div class="p-6 border-t bg-gray-50">
            <button onclick="document.body.removeChild(this.closest('.fixed'))" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                Close
            </button>
        </div>
    `;
    
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
}