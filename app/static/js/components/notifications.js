// Handle notification form response
function handleNotificationResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const statusDiv = document.getElementById('notification-status');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        showNotification('Notification configuration added successfully!', 'success');
        form.reset();
        statusDiv.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded-lg p-3">
                <span class="text-green-700 text-sm">Notification configuration added successfully!</span>
            </div>
        `;
        // Trigger HTMX refresh for notification list
        document.body.dispatchEvent(new CustomEvent('notificationUpdate'));
    } else {
        // Error
        let errorMessage = 'Failed to add notification configuration';
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

// Test notification configuration
async function testNotificationConfig(configId) {
    try {
        const response = await fetch(`/api/notifications/${configId}/test`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.status === 'success') {
                showNotification(result.message, 'success');
            } else {
                showNotification(result.message, 'error');
            }
        } else {
            const error = await response.json();
            showNotification(`Test failed: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Test failed: ${error.message}`, 'error');
    }
}

// Toggle notification configuration
async function toggleNotificationConfig(configId, enabled) {
    const action = enabled ? 'disable' : 'enable';
    
    try {
        const response = await fetch(`/api/notifications/${configId}/${action}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification(`Notification ${action}d successfully!`, 'success');
            document.body.dispatchEvent(new CustomEvent('notificationUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to ${action} notification: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to ${action} notification: ${error.message}`, 'error');
    }
}

// Delete notification configuration
async function deleteNotificationConfig(configId, configName) {
    if (!confirm(`Are you sure you want to delete the notification configuration "${configName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/notifications/${configId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Notification configuration deleted successfully!', 'success');
            document.body.dispatchEvent(new CustomEvent('notificationUpdate'));
        } else {
            const error = await response.json();
            showNotification(`Failed to delete notification configuration: ${error.detail}`, 'error');
        }
    } catch (error) {
        showNotification(`Failed to delete notification configuration: ${error.message}`, 'error');
    }
}