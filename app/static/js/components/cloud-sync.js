// Cloud Sync Provider Field Toggle
function toggleProviderFields() {
    const provider = document.getElementById('provider-select').value;
    const s3Fields = document.getElementById('s3-fields');
    const sftpFields = document.getElementById('sftp-fields');
    const submitButton = document.getElementById('submit-button');
    
    if (provider === 's3') {
        s3Fields.style.display = 'block';
        sftpFields.style.display = 'none';
        submitButton.textContent = 'Add S3 Location';
    } else if (provider === 'sftp') {
        s3Fields.style.display = 'none';
        sftpFields.style.display = 'block';
        submitButton.textContent = 'Add SFTP Location';
    }
}

// Handle cloud sync form response
function handleCloudSyncResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const statusDiv = document.getElementById('cloud-sync-status');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        showNotification('Cloud sync location added successfully!', 'success');
        form.reset();
        // Reset provider selection to S3 and update fields
        document.getElementById('provider-select').value = 's3';
        toggleProviderFields();
        statusDiv.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded-lg p-3">
                <span class="text-green-700 text-sm">Cloud sync location configured successfully!</span>
            </div>
        `;
        
        // Trigger HTMX refresh for cloud sync list
        document.body.dispatchEvent(new CustomEvent('cloudSyncUpdate'));
    } else {
        // Error
        let errorMessage = 'Failed to add cloud sync location';
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

// Test cloud sync connection
async function testCloudSyncConnection(configId, buttonElement) {
    const originalText = buttonElement.textContent;
    buttonElement.disabled = true;
    buttonElement.textContent = 'Testing...';
    
    try {
        const response = await fetch(`/api/cloud-sync/${configId}/test`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            
            if (result.status === 'success') {
                let message = 'Connection test successful!';
                if (result.details) {
                    message += ` (Read: ${result.details.read_test}, Write: ${result.details.write_test})`;
                }
                showNotification(message, 'success');
            } else if (result.status === 'warning') {
                showNotification(`Connection test warning: ${result.message}`, 'warning');
            } else {
                showNotification(`Connection test failed: ${result.message}`, 'error');
            }
        } else {
            const error = await response.json();
            showNotification(`Connection test failed: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Connection test failed: ${error.message}`, 'error');
    } finally {
        buttonElement.disabled = false;
        buttonElement.textContent = originalText;
    }
}

// Toggle cloud sync configuration
async function toggleCloudSyncConfig(configId, enabled, buttonElement) {
    const action = enabled ? 'disable' : 'enable';
    const originalText = buttonElement.textContent;
    buttonElement.disabled = true;
    buttonElement.textContent = enabled ? 'Disabling...' : 'Enabling...';
    
    try {
        const response = await fetch(`/api/cloud-sync/${configId}/${action}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification(`Cloud sync ${action}d successfully!`, 'success');
            document.body.dispatchEvent(new CustomEvent('cloudSyncUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to ${action} cloud sync: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to ${action} cloud sync: ${error.message}`, 'error');
    } finally {
        buttonElement.disabled = false;
        buttonElement.textContent = originalText;
    }
}

// Delete cloud sync configuration
async function deleteCloudSyncConfig(configId, configName, buttonElement) {
    if (!confirm(`Are you sure you want to delete the cloud sync configuration "${configName}"?`)) {
        return;
    }
    
    const originalText = buttonElement.textContent;
    buttonElement.disabled = true;
    buttonElement.textContent = 'Deleting...';
    
    try {
        const response = await fetch(`/api/cloud-sync/${configId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Cloud sync configuration deleted successfully!', 'success');
            document.body.dispatchEvent(new CustomEvent('cloudSyncUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to delete cloud sync configuration: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to delete cloud sync configuration: ${error.message}`, 'error');
    } finally {
        buttonElement.disabled = false;
        buttonElement.textContent = originalText;
    }
}