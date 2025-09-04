// Debug functionality

function loadDebugInfo() {
    const container = document.getElementById('debug-info-container');
    if (!container) return;

    // Show loading state
    container.innerHTML = `
        <div class="text-center py-8">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p class="text-gray-500">Loading debug information...</p>
        </div>
    `;

    // Load debug info via HTMX
    htmx.ajax('GET', '/api/debug/html', {
        target: '#debug-info-container',
        swap: 'innerHTML'
    });
}

function refreshDebugInfo() {
    const refreshBtn = document.getElementById('refresh-debug-btn');
    if (refreshBtn) {
        // Show loading state on button
        const originalContent = refreshBtn.innerHTML;
        refreshBtn.innerHTML = `
            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            <span>Loading...</span>
        `;
        refreshBtn.disabled = true;
        
        // Load debug info
        loadDebugInfo();
        
        // Restore button after a delay
        setTimeout(() => {
            refreshBtn.innerHTML = originalContent;
            refreshBtn.disabled = false;
        }, 1500);
    }
}