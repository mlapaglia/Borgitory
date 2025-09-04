// Archives functionality
function populateArchiveRepositorySelect() {
    const select = document.getElementById('archive-repository-select');
    if (!window.borgitoryAppInstance || !window.borgitoryAppInstance.repositories) {
        return;
    }
    
    // Clear existing options except the first one
    select.innerHTML = '<option value="">Select a repository to view archives...</option>';
    
    // Add repository options
    window.borgitoryAppInstance.repositories.forEach(repo => {
        const option = document.createElement('option');
        option.value = repo.id;
        option.textContent = repo.name;
        select.appendChild(option);
    });
}

function loadArchives() {
    const select = document.getElementById('archive-repository-select');
    const refreshBtn = document.getElementById('refresh-archives-btn');
    const archivesList = document.getElementById('archives-list');
    
    const repositoryId = select.value;
    
    if (!repositoryId) {
        refreshBtn.disabled = true;
        archivesList.innerHTML = `
            <div class="text-gray-500 text-center py-8">
                <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                </svg>
                <p>Select a repository above to view its archives</p>
            </div>
        `;
        return;
    }
    
    refreshBtn.disabled = false;
    
    // Show loading state
    archivesList.innerHTML = `
        <div class="text-center py-8">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p class="text-gray-500">Loading archives...</p>
        </div>
    `;
    
    // Load archives via HTMX
    htmx.ajax('GET', `/api/repositories/${repositoryId}/archives/html`, {
        target: '#archives-list',
        swap: 'innerHTML'
    });
}

function refreshArchives() {
    loadArchives();
}