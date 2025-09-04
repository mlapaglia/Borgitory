// Job History UI Functions

// Make functions globally available
window.toggleJobDetails = function(jobId) {
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

window.toggleTaskDetails = function(jobId, taskOrder) {
    const detailsDiv = document.getElementById(`task-details-${jobId}-${taskOrder}`);
    const chevronIcon = document.getElementById(`task-chevron-${jobId}-${taskOrder}`);
    
    if (detailsDiv) {
        if (detailsDiv.classList.contains('hidden')) {
            detailsDiv.classList.remove('hidden');
            chevronIcon.style.transform = 'rotate(180deg)';
            
            // Initialize live output streaming for running tasks
            const outputDiv = document.getElementById(`task-output-${jobId}-${taskOrder}`);
            if (outputDiv && outputDiv.dataset.jobUuid) {
                initializeTaskLiveOutput(outputDiv.dataset.jobUuid, taskOrder, outputDiv);
            }
        } else {
            detailsDiv.classList.add('hidden');
            chevronIcon.style.transform = 'rotate(0deg)';
            
            // Clean up SSE connection when collapsing
            const outputDiv = document.getElementById(`task-output-${jobId}-${taskOrder}`);
            if (outputDiv && outputDiv.liveOutputSource) {
                outputDiv.liveOutputSource.close();
                outputDiv.liveOutputSource = null;
            }
        }
    }
}

window.copyJobOutput = function(jobId) {
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

window.copyTaskOutput = function(jobId, taskOrder) {
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

window.viewRunningJobDetails = function(jobId) {
    console.log(`Switching to jobs tab for job: ${jobId}`);
    
    // Switch to the jobs tab
    if (typeof switchTab === 'function') {
        switchTab('jobs');
    } else {
        console.error('switchTab function not found');
    }
    
    // Load job history with auto-expansion for this job
    htmx.ajax('GET', `/api/jobs/html?expand=${jobId}`, {
        target: '#job-history',
        swap: 'innerHTML'
    });
    
    // Show notification
    showNotification(`Showing details for job ${jobId.substring(0, 8)}`, 'info');
}

// Initialize live output streaming for individual task
function initializeTaskLiveOutput(jobUuid, taskIndex, outputElement) {
    if (!jobUuid || outputElement.liveOutputSource) {
        return; // Already connected or no job UUID
    }
    
    // Connect to the individual job stream endpoint
    const eventSource = new EventSource(`/api/jobs/${jobUuid}/stream`);
    outputElement.liveOutputSource = eventSource;
    
    eventSource.onopen = function(event) {
        outputElement.innerHTML = '<div class="text-gray-500">Connected to live output...</div>';
    };
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'task_output' && data.task_index === parseInt(taskIndex)) {
                // Clear the "Connecting..." message on first real output
                if (outputElement.innerHTML.includes('Connected to live output')) {
                    outputElement.innerHTML = '';
                }
                
                // Add the new line
                const lineElement = document.createElement('div');
                lineElement.textContent = data.line;
                outputElement.appendChild(lineElement);
                
                // Auto-scroll to bottom
                outputElement.scrollTop = outputElement.scrollHeight;
            } else if (data.type === 'task_completed' && data.task_index === parseInt(taskIndex)) {
                // Task completed, close connection
                eventSource.close();
                outputElement.liveOutputSource = null;
                
                // Add completion indicator
                const completionElement = document.createElement('div');
                completionElement.className = 'text-blue-400 mt-2';
                completionElement.textContent = `--- Task completed (${data.status}) ---`;
                outputElement.appendChild(completionElement);
            }
        } catch (error) {
            // Silently handle parsing errors
        }
    };
    
    eventSource.onerror = function(event) {
        outputElement.innerHTML = '<div class="text-red-400">Connection error - refresh to retry</div>';
        eventSource.close();
        outputElement.liveOutputSource = null;
    };
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