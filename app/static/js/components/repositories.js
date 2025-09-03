// Repository Tab Functions  
function switchRepositoryTab(tab) {
    const createTab = document.getElementById('create-tab');
    const importTab = document.getElementById('import-tab');
    const createForm = document.getElementById('create-form');
    const importForm = document.getElementById('import-form');
    
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

// Handle import repository start (loading state)
function handleImportStart(event) {
    const submitButton = document.getElementById('import-submit');
    const buttonText = document.getElementById('import-button-text');
    const spinner = document.getElementById('import-loading-spinner');
    
    // Show loading state
    submitButton.disabled = true;
    submitButton.className = 'w-full bg-blue-400 text-white px-4 py-2 rounded-md cursor-not-allowed flex items-center justify-center';
    buttonText.textContent = 'Importing...';
    spinner.classList.remove('hidden');
}

// Handle import repository response
function handleImportResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const submitButton = document.getElementById('import-submit');
    const buttonText = document.getElementById('import-button-text');
    const spinner = document.getElementById('import-loading-spinner');
    
    // Hide loading state immediately
    spinner.classList.add('hidden');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        buttonText.textContent = 'Import Repository';
        showNotification('Repository imported successfully!', 'success');
        form.reset();
        
        // Reset form state
        document.getElementById('encryption-info').classList.add('hidden');
        document.getElementById('passphrase-field').classList.add('hidden');
        document.getElementById('keyfile-field').classList.add('hidden');
        document.getElementById('repo-select').value = '';
        
        // Reset button to disabled state
        submitButton.disabled = true;
        submitButton.className = 'w-full bg-gray-400 text-white px-4 py-2 rounded-md cursor-not-allowed flex items-center justify-center';
        buttonText.textContent = 'Select a repository first';
        
        // Trigger HTMX refresh for repository list
        document.body.dispatchEvent(new CustomEvent('repositoryUpdate'));
    } else {
        // Error - re-enable button immediately
        buttonText.textContent = 'Import Repository';
        submitButton.disabled = false;
        submitButton.className = 'w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 flex items-center justify-center';
        
        // Parse and show error message immediately
        let errorMessage = 'Failed to import repository';
        try {
            const errorData = JSON.parse(xhr.response);
            if (errorData.detail) {
                errorMessage = Array.isArray(errorData.detail) 
                    ? errorData.detail.map(err => `${err.loc?.join('.')}: ${err.msg}`).join(', ')
                    : errorData.detail;
            }
        } catch (e) {
            errorMessage = `HTTP ${xhr.status}: ${xhr.statusText}`;
        }
        showNotification(errorMessage, 'error');
    }
}

// Handle repository form start (for create form loading state)
function handleCreateRepositoryStart(event) {
    const submitButton = document.getElementById('create-repo-button');
    const buttonText = document.getElementById('create-repo-text');
    const spinner = document.getElementById('create-repo-spinner');
    
    // Show loading state
    submitButton.disabled = true;
    submitButton.className = 'w-full bg-blue-400 text-white px-4 py-2 rounded-md cursor-not-allowed flex items-center justify-center';
    buttonText.textContent = 'Creating...';
    spinner.classList.remove('hidden');
}

// Handle repository form response (for create form)
function handleRepositoryResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const submitButton = document.getElementById('create-repo-button');
    const buttonText = document.getElementById('create-repo-text');
    const spinner = document.getElementById('create-repo-spinner');
    
    // Always hide loading state first
    spinner.classList.add('hidden');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        submitButton.disabled = false;
        submitButton.className = 'w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center justify-center';
        buttonText.textContent = 'Create Repository';
        
        showNotification('Repository added successfully!', 'success');
        form.reset();
        // Trigger HTMX refresh for repository list
        document.body.dispatchEvent(new CustomEvent('repositoryUpdate'));
    } else {
        // Error - re-enable button
        submitButton.disabled = false;
        submitButton.className = 'w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center justify-center';
        buttonText.textContent = 'Create Repository';
        
        let errorMessage = 'Failed to add repository';
        try {
            const errorData = JSON.parse(xhr.response);
            if (errorData.detail) {
                if (Array.isArray(errorData.detail)) {
                    // Validation errors
                    errorMessage = errorData.detail.map(err => 
                        `${err.loc?.join('.')}: ${err.msg}`
                    ).join(', ');
                } else {
                    // String error message
                    errorMessage = errorData.detail;
                }
            }
        } catch (e) {
            // Fallback error message
            errorMessage = `HTTP ${xhr.status}: ${xhr.statusText}`;
        }
        showNotification(errorMessage, 'error');
    }
}

// Repository scanning functions
async function scanForRepositories() {
    const statusDiv = document.getElementById('scan-status');
    const repoSelect = document.getElementById('repo-select');
    const discoveredRepos = document.getElementById('discovered-repos');
    
    statusDiv.innerHTML = '<div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div> Scanning...';
    
    try {
        const response = await fetch('/api/repositories/scan');
        const data = await response.json();
        
        if (data.repositories && data.repositories.length > 0) {
            // Clear and populate select
            repoSelect.innerHTML = '<option value="">Select a repository...</option>';
            data.repositories.forEach(repo => {
                const option = document.createElement('option');
                option.value = JSON.stringify(repo);
                option.textContent = `${repo.path} (${repo.encryption_mode})`;
                repoSelect.appendChild(option);
            });
            
            discoveredRepos.classList.remove('hidden');
            statusDiv.innerHTML = `Found ${data.repositories.length} repositories`;
        } else {
            statusDiv.innerHTML = 'No repositories found';
        }
    } catch (error) {
        statusDiv.innerHTML = `Error: ${error.message}`;
    }
}

function selectDiscoveredRepo() {
    const repoSelect = document.getElementById('repo-select');
    const importPath = document.getElementById('import-path');
    const submitButton = document.getElementById('import-submit');
    const buttonText = document.getElementById('import-button-text');
    const encryptionInfo = document.getElementById('encryption-info');
    const encryptionText = document.getElementById('encryption-text');
    const passphraseField = document.getElementById('passphrase-field');
    const keyfileField = document.getElementById('keyfile-field');
    
    if (!repoSelect.value) {
        importPath.value = '';
        submitButton.disabled = true;
        submitButton.className = 'w-full bg-gray-400 text-white px-4 py-2 rounded-md cursor-not-allowed flex items-center justify-center';
        buttonText.textContent = 'Select a repository first';
        encryptionInfo.classList.add('hidden');
        passphraseField.classList.add('hidden');
        keyfileField.classList.add('hidden');
        return;
    }
    
    try {
        const repo = JSON.parse(repoSelect.value);
        importPath.value = repo.path;
        
        // Show encryption info
        encryptionText.textContent = repo.preview || `Encryption: ${repo.encryption_mode}`;
        encryptionInfo.classList.remove('hidden');
        
        // Show appropriate auth fields based on encryption mode
        if (repo.requires_keyfile) {
            keyfileField.classList.remove('hidden');
            passphraseField.classList.remove('hidden'); // Most repos also need passphrase
        } else if (repo.encryption_mode !== 'none') {
            passphraseField.classList.remove('hidden');
            keyfileField.classList.add('hidden');
        } else {
            passphraseField.classList.add('hidden');
            keyfileField.classList.add('hidden');
        }
        
        // Enable submit button
        submitButton.disabled = false;
        submitButton.className = 'w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 flex items-center justify-center';
        buttonText.textContent = 'Import Repository';
    } catch (error) {
        console.error('Error parsing repository data:', error);
    }
}