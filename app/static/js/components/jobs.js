// Job History UI Functions
window.copyJobOutput = function(jobId) {
    const outputDiv = document.getElementById(`job-output-${jobId}`);
    if (outputDiv) {
        const text = outputDiv.textContent || outputDiv.innerText;
        navigator.clipboard.writeText(text).then(() => {
            showHTMXNotification('Job output copied to clipboard', 'success');
        }).catch(err => {
            console.error('Failed to copy job output: ', err);
            showHTMXNotification('Failed to copy job output', 'error');
        });
    }
}

window.copyTaskOutput = function(jobId, taskOrder) {
    const outputDiv = document.getElementById(`task-output-${jobId}-${taskOrder}`);
    if (outputDiv) {
        const text = outputDiv.textContent || outputDiv.innerText;
        navigator.clipboard.writeText(text).then(() => {
            showHTMXNotification('Task output copied to clipboard', 'success');
        }).catch(err => {
            console.error('Failed to copy task output: ', err);
            showHTMXNotification('Failed to copy task output', 'error');
        });
    }
}

function showHTMXNotification(message, type, targetContainer = null) {
    // Try to find the best notification container
    let target = null;
    
    if (targetContainer) {
        target = document.querySelector(targetContainer);
    }
    
    if (!target) {
        // Try common job-related containers first
        const containers = ['#backup-status', '#job-status', '#notification-status', '[id$="-status"]'];
        for (const containerSelector of containers) {
            target = document.querySelector(containerSelector);
            if (target) break;
        }
    }
    
    if (!target) {
        // Create temporary container if none exists
        const tempContainer = document.createElement('div');
        tempContainer.id = 'temp-notification';
        tempContainer.style.position = 'fixed';
        tempContainer.style.top = '20px';
        tempContainer.style.right = '20px';
        tempContainer.style.zIndex = '1000';
        document.body.appendChild(tempContainer);
        target = tempContainer;
    }
    
    htmx.ajax('GET', `/api/shared/notification?type=${type}&message=${encodeURIComponent(message)}`, {
        target: target,
        swap: 'innerHTML'
    });
}