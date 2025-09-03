// Job History UI Functions

function toggleJobDetails(jobId) {
    const detailsDiv = document.getElementById(`job-details-${jobId}`);
    const chevronIcon = document.getElementById(`chevron-${jobId}`);
    
    if (detailsDiv) {
        if (detailsDiv.classList.contains('hidden')) {
            detailsDiv.classList.remove('hidden');
            chevronIcon.style.transform = 'rotate(180deg)';
        } else {
            detailsDiv.classList.add('hidden');
            chevronIcon.style.transform = 'rotate(0deg)';
        }
    }
}

function toggleTaskDetails(jobId, taskOrder) {
    const detailsDiv = document.getElementById(`task-details-${jobId}-${taskOrder}`);
    const chevronIcon = document.getElementById(`task-chevron-${jobId}-${taskOrder}`);
    
    if (detailsDiv) {
        if (detailsDiv.classList.contains('hidden')) {
            detailsDiv.classList.remove('hidden');
            chevronIcon.style.transform = 'rotate(180deg)';
        } else {
            detailsDiv.classList.add('hidden');
            chevronIcon.style.transform = 'rotate(0deg)';
        }
    }
}

function copyJobOutput(jobId) {
    const outputDiv = document.getElementById(`job-output-${jobId}`);
    if (outputDiv) {
        const text = outputDiv.textContent || outputDiv.innerText;
        navigator.clipboard.writeText(text).then(() => {
            showNotification('Job output copied to clipboard', 'success');
        }).catch(err => {
            console.error('Failed to copy job output: ', err);
            showNotification('Failed to copy job output', 'error');
        });
    }
}

function copyTaskOutput(jobId, taskOrder) {
    const outputDiv = document.getElementById(`task-output-${jobId}-${taskOrder}`);
    if (outputDiv) {
        const text = outputDiv.textContent || outputDiv.innerText;
        navigator.clipboard.writeText(text).then(() => {
            showNotification('Task output copied to clipboard', 'success');
        }).catch(err => {
            console.error('Failed to copy task output: ', err);
            showNotification('Failed to copy task output', 'error');
        });
    }
}

function viewRunningJobDetails(jobId) {
    // Navigate to job details view or open a modal
    // For now, just show an alert with the job ID
    console.log(`Viewing details for running job: ${jobId}`);
    
    // You could expand this to:
    // - Open a modal with live job output
    // - Navigate to a dedicated job details page  
    // - Show more detailed progress information
    showNotification(`Viewing job ${jobId.substring(0, 8)}...`, 'info');
}

// Helper function for showing notifications (assumes it exists in utils.js)
function showNotification(message, type = 'info') {
    // Check if a different showNotification exists globally, avoiding self-reference
    if (typeof window.showNotification === 'function' && window.showNotification !== showNotification) {
        window.showNotification(message, type);
    } else {
        // Simple fallback notification
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 px-4 py-2 rounded-lg text-white z-50 ${
            type === 'success' ? 'bg-green-500' : 
            type === 'error' ? 'bg-red-500' : 
            'bg-blue-500'
        }`;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
}