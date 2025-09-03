// Handle backup form response
function handleBackupResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const statusDiv = document.getElementById('backup-status');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success - backup started
        try {
            const response = JSON.parse(xhr.response);
            showNotification('Backup started successfully!', 'success');
            statusDiv.innerHTML = `
                <div id="backup-job-${response.job_id}" class="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <div class="flex items-center">
                        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                        <span class="text-blue-700 text-sm">Backup job #${response.job_id} started... (This may take a few minutes if Docker images need to be downloaded)</span>
                    </div>
                </div>
            `;
            
            // Store the job ID for status updates
            statusDiv.setAttribute('data-backup-job-id', response.job_id);
        } catch (e) {
            showNotification('Backup started!', 'success');
        }
    } else {
        // Error
        let errorMessage = 'Failed to start backup';
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
        statusDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-3">
                <span class="text-red-700 text-sm">${errorMessage}</span>
            </div>
        `;
    }
}