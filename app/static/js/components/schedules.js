// Schedule helper functions
function updateCronExpression() {
    const preset = document.getElementById('schedule-preset');
    const customCron = document.getElementById('custom-cron');
    const cronExpression = document.getElementById('cron-expression');
    const cronDescription = document.getElementById('cron-description');
    
    if (preset.value === 'custom') {
        customCron.classList.remove('hidden');
        // Copy current custom input value to hidden field
        const customInput = document.getElementById('custom-cron-input');
        cronExpression.value = customInput.value.trim();
        cronDescription.classList.add('hidden');
    } else if (preset.value) {
        customCron.classList.add('hidden');
        cronExpression.value = preset.value;
        cronDescription.textContent = preset.options[preset.selectedIndex].text;
        cronDescription.classList.remove('hidden');
    } else {
        customCron.classList.add('hidden');
        cronExpression.value = '';
        cronDescription.classList.add('hidden');
    }
}

function updateCustomCronExpression() {
    const preset = document.getElementById('schedule-preset');
    const customInput = document.getElementById('custom-cron-input');
    const cronExpression = document.getElementById('cron-expression');
    
    // Only update if custom is selected
    if (preset.value === 'custom') {
        cronExpression.value = customInput.value.trim();
    }
}

function prepareScheduleSubmission(event) {
    // Ensure custom cron expression is copied to hidden field before submission
    const preset = document.getElementById('schedule-preset');
    const customInput = document.getElementById('custom-cron-input');
    const cronExpression = document.getElementById('cron-expression');
    
    if (preset.value === 'custom' && customInput) {
        const customValue = customInput.value.trim();
        if (!customValue) {
            event.preventDefault();
            showNotification('Please enter a custom cron expression', 'error');
            return false;
        }
        cronExpression.value = customValue;
    }
    
    // Validate that we have a cron expression
    if (!cronExpression.value.trim()) {
        event.preventDefault();
        showNotification('Please select a schedule or enter a custom cron expression', 'error');
        return false;
    }
    
    return true;
}

// Handle schedule form response
function handleScheduleResponse(event) {
    const xhr = event.detail.xhr;
    const form = event.target;
    const statusDiv = document.getElementById('schedule-status');
    
    if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        showNotification('Schedule created successfully!', 'success');
        form.reset();
        statusDiv.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded-lg p-3">
                <span class="text-green-700 text-sm">Schedule created successfully!</span>
            </div>
        `;
        
        // Clear form fields
        document.getElementById('schedule-preset').value = '';
        document.getElementById('cron-expression').value = '';
        document.getElementById('custom-cron').classList.add('hidden');
        document.getElementById('cron-description').classList.add('hidden');
        
        // Trigger HTMX refresh for schedule list
        document.body.dispatchEvent(new CustomEvent('scheduleUpdate'));
    } else {
        // Error
        let errorMessage = 'Failed to create schedule';
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

// Upcoming backups loading functions
function showUpcomingLoading() {
    const upcomingDiv = document.getElementById('upcoming-backups');
    if (upcomingDiv && !upcomingDiv.querySelector('.loading-indicator')) {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'loading-indicator text-blue-500 text-sm flex items-center';
        loadingDiv.innerHTML = '<div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>Updating upcoming backups...';
        upcomingDiv.appendChild(loadingDiv);
    }
}

function hideUpcomingLoading() {
    const upcomingDiv = document.getElementById('upcoming-backups');
    if (upcomingDiv) {
        const loadingIndicator = upcomingDiv.querySelector('.loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }
    }
}