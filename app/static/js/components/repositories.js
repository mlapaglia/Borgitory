// Repository Tab Functions  
function switchRepositoryTab(tab) {
    const createTab = document.getElementById('create-tab');
    const importTab = document.getElementById('import-tab');
    const createForm = document.getElementById('create-form-container');
    const importForm = document.getElementById('import-form-container');
    
    if (tab === 'create') {
        createTab.classList.add('text-blue-600', 'border-blue-600');
        createTab.classList.remove('text-gray-500');
        importTab.classList.add('text-gray-500');
        importTab.classList.remove('text-blue-600', 'border-blue-600');
        
        createForm.classList.remove('hidden');
        importForm.classList.add('hidden');
    } else {
        importTab.classList.add('text-blue-600', 'border-blue-600');
        importTab.classList.remove('text-gray-500');
        createTab.classList.add('text-gray-500');
        createTab.classList.remove('text-blue-600', 'border-blue-600');
        
        importForm.classList.remove('hidden');
        createForm.classList.add('hidden');
    }
}

// selectDiscoveredRepo function removed - now handled by HTMX
// Dynamic form updates happen via /api/repositories/import-form-update endpoint