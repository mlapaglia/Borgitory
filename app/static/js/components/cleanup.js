// Handle cleanup config form response
function handleCleanupConfigResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const statusDiv = document.getElementById('cleanup-config-status');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        showNotification('Cleanup policy created successfully!', 'success');
        form.reset();
        statusDiv.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded-lg p-3">
                <span class="text-green-700 text-sm">Cleanup policy created successfully!</span>
            </div>
        `;
        // Trigger HTMX refresh for cleanup config list
        document.body.dispatchEvent(new CustomEvent('cleanupConfigUpdate'));
    } else {
        // Error
        let errorMessage = 'Failed to create cleanup policy';
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
        statusDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-3">
                <span class="text-red-700 text-sm">${errorMessage}</span>
            </div>
        `;
    }
}

// Toggle cleanup configuration
async function toggleCleanupConfig(configId, enabled) {
    const action = enabled ? 'disable' : 'enable';
    
    try {
        const response = await fetch(`/api/cleanup/${configId}/${action}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification(`Cleanup policy ${action}d successfully!`, 'success');
            document.body.dispatchEvent(new CustomEvent('cleanupConfigUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to ${action} cleanup policy: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to ${action} cleanup policy: ${error.message}`, 'error');
    }
}

// Delete cleanup configuration
async function deleteCleanupConfig(configId, configName) {
    if (!confirm(`Are you sure you want to delete the cleanup policy "${configName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/cleanup/${configId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Cleanup policy deleted successfully!', 'success');
            document.body.dispatchEvent(new CustomEvent('cleanupConfigUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to delete cleanup policy: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to delete cleanup policy: ${error.message}`, 'error');
    }
}

// Handle prune form response
function handlePruneResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const statusDiv = document.getElementById('prune-status');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success - prune started
        try {
            const response = JSON.parse(xhr.response);
            showNotification('Archive cleanup started!', 'success');
            statusDiv.innerHTML = `
                <div id="prune-job-${response.job_id}" class="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <div class="flex items-center">
                        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                        <span class="text-blue-700 text-sm">Archive cleanup job #${response.job_id} started...</span>
                    </div>
                </div>
            `;
        } catch (e) {
            showNotification('Archive cleanup started!', 'success');
        }
    } else {
        // Error
        let errorMessage = 'Failed to start archive cleanup';
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
        statusDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-3">
                <span class="text-red-700 text-sm">${errorMessage}</span>
            </div>
        `;
    }
}

// Handle strategy radio button changes
function toggleRetentionStrategy() {
    const simpleRadio = document.getElementById('strategy-simple');
    const advancedRadio = document.getElementById('strategy-advanced');
    const simpleDiv = document.getElementById('simple-strategy');
    const advancedDiv = document.getElementById('advanced-strategy');
    
    if (simpleRadio.checked) {
        simpleDiv.classList.remove('hidden');
        advancedDiv.classList.add('hidden');
    } else if (advancedRadio.checked) {
        simpleDiv.classList.add('hidden');
        advancedDiv.classList.remove('hidden');
    }
}