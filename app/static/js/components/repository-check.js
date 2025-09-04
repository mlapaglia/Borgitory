// Repository Check functionality

// Helper function to escape HTML
function escapeHtml(unsafe) {
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

// Initialize repository check tab when it becomes active
function initRepositoryCheck() {
    loadRepositoryCheckRepositories();
    loadCheckPolicies();
    loadCheckHistory();
}

// Load repositories for repository check
function loadRepositoryCheckRepositories() {
    const repositorySelect = document.getElementById('check-repository-select');
    if (!repositorySelect) return;
    
    // Get repositories from global app instance
    if (window.borgitoryAppInstance && window.borgitoryAppInstance.repositories) {
        repositorySelect.innerHTML = '<option value="">Select Repository...</option>';
        window.borgitoryAppInstance.repositories.forEach(repo => {
            const option = document.createElement('option');
            option.value = repo.id;
            option.textContent = repo.name;
            repositorySelect.appendChild(option);
        });
    }
}

// Load check policies
async function loadCheckPolicies() {
    try {
        const response = await fetch('/api/repository-check-configs/');
        if (response.ok) {
            const policies = await response.json();
            displayCheckPolicies(policies);
            populateCheckPolicySelect(policies);
        } else {
            showCheckPoliciesError('Failed to load check policies');
        }
    } catch (error) {
        console.error('Error loading check policies:', error);
        showCheckPoliciesError('Error loading check policies');
    }
}

// Display check policies list
function displayCheckPolicies(policies) {
    const container = document.getElementById('check-policies-list');
    if (!container) return;
    
    if (policies.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4">
                <p class="text-gray-500">No check policies created yet</p>
                <p class="text-xs text-gray-400 mt-1">Create your first policy above</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = policies.map(policy => `
        <div class="border rounded-lg p-4 mb-3">
            <div class="flex items-center justify-between">
                <div class="flex-1">
                    <h4 class="font-medium text-gray-900">${escapeHtml(policy.name)}</h4>
                    ${policy.description ? `<p class="text-sm text-gray-600 mt-1">${escapeHtml(policy.description)}</p>` : ''}
                    <div class="flex items-center space-x-4 mt-2 text-xs text-gray-500">
                        <span class="px-2 py-1 bg-blue-100 text-blue-800 rounded">${formatCheckType(policy.check_type)}</span>
                        ${policy.verify_data ? '<span class="px-2 py-1 bg-purple-100 text-purple-800 rounded">Data Verification</span>' : ''}
                        ${policy.repair_mode ? '<span class="px-2 py-1 bg-red-100 text-red-800 rounded">Repair Mode</span>' : ''}
                        ${policy.save_space ? '<span class="px-2 py-1 bg-green-100 text-green-800 rounded">Space Saving</span>' : ''}
                    </div>
                </div>
                <div class="flex items-center space-x-2 ml-4">
                    <button onclick="editCheckPolicy(${policy.id})" class="text-blue-600 hover:text-blue-800 text-sm">
                        Edit
                    </button>
                    <button onclick="deleteCheckPolicy(${policy.id})" class="text-red-600 hover:text-red-800 text-sm">
                        Delete
                    </button>
                    <div class="flex items-center">
                        <input type="checkbox" ${policy.enabled ? 'checked' : ''} onchange="toggleCheckPolicy(${policy.id})" class="mr-1">
                        <span class="text-xs text-gray-500">Enabled</span>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

// Populate check policy dropdown
function populateCheckPolicySelect(policies) {
    const select = document.getElementById('check-policy-select');
    if (!select) return;
    
    // Keep the "Custom Check" option
    select.innerHTML = '<option value="">Custom Check...</option>';
    
    policies.filter(p => p.enabled).forEach(policy => {
        const option = document.createElement('option');
        option.value = policy.id;
        option.textContent = `${policy.name} (${formatCheckType(policy.check_type)})`;
        select.appendChild(option);
    });
}

// Format check type for display
function formatCheckType(checkType) {
    switch (checkType) {
        case 'full':
            return 'Full Check';
        case 'repository_only':
            return 'Repository Only';
        case 'archives_only':
            return 'Archives Only';
        default:
            return checkType;
    }
}

// Show check policies error
function showCheckPoliciesError(message) {
    const container = document.getElementById('check-policies-list');
    if (container) {
        container.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <div class="flex items-center">
                    <svg class="w-5 h-5 text-red-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span class="text-red-700">${message}</span>
                </div>
            </div>
        `;
    }
}

// Handle check policy form response
function handleCheckPolicyResponse(event) {
    const statusDiv = document.getElementById('check-policy-status');
    const form = document.getElementById('check-policy-form');
    
    if (event.detail.xhr.status === 200 || event.detail.xhr.status === 201) {
        showNotification('Check policy created successfully', 'success');
        form.reset();
        loadCheckPolicies(); // Refresh the policies list
        statusDiv.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                <div class="flex items-center">
                    <svg class="w-5 h-5 text-green-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    <span class="text-green-700">Check policy created successfully</span>
                </div>
            </div>
        `;
    } else {
        const errorMessage = event.detail.xhr.responseText || 'Failed to create check policy';
        statusDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <div class="flex items-center">
                    <svg class="w-5 h-5 text-red-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span class="text-red-700">Error: ${errorMessage}</span>
                </div>
            </div>
        `;
    }
    
    // Clear status after 5 seconds
    setTimeout(() => {
        statusDiv.innerHTML = '';
    }, 5000);
}


// Handle manual check response
function handleCheckResponse(event) {
    const statusDiv = document.getElementById('check-status');
    
    if (event.detail.xhr.status === 200 || event.detail.xhr.status === 201) {
        const response = JSON.parse(event.detail.xhr.responseText);
        showNotification('Repository check started', 'success');
        statusDiv.innerHTML = `
            <div id="check-job-${response.job_id}" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div class="flex items-center">
                    <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                    <span class="text-blue-700 progress-text">Check job started (ID: ${response.job_id})</span>
                </div>
            </div>
        `;
        loadCheckHistory(); // Refresh history
    } else {
        const errorMessage = event.detail.xhr.responseText || 'Failed to start repository check';
        statusDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <div class="flex items-center">
                    <svg class="w-5 h-5 text-red-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span class="text-red-700">Error: ${errorMessage}</span>
                </div>
            </div>
        `;
    }
    
    // Clear status after 10 seconds
    setTimeout(() => {
        statusDiv.innerHTML = '';
    }, 10000);
}

// Update check options based on check type
function updateCheckOptions() {
    const checkType = document.querySelector('input[name="check_type"]:checked')?.value;
    const verifyDataOption = document.getElementById('verify-data-option');
    const repairModeCheckbox = document.getElementById('repair-mode-checkbox');
    const timeLimitSection = document.getElementById('time-limit-section');
    const archiveFiltersSection = document.getElementById('archive-filters-section');
    
    if (checkType === 'repository_only') {
        // Disable verify_data for repository_only
        verifyDataOption.style.opacity = '0.5';
        verifyDataOption.querySelector('input').disabled = true;
        verifyDataOption.querySelector('input').checked = false;
        
        // Show time limit section
        if (timeLimitSection) timeLimitSection.style.display = 'block';
        
        // Hide archive filters
        if (archiveFiltersSection) archiveFiltersSection.style.display = 'none';
    } else {
        // Enable verify_data for full and archives_only
        verifyDataOption.style.opacity = '1';
        verifyDataOption.querySelector('input').disabled = false;
        
        // Hide time limit section
        if (timeLimitSection) timeLimitSection.style.display = 'none';
        
        // Show archive filters
        if (archiveFiltersSection) archiveFiltersSection.style.display = 'block';
    }
    
    // Handle repair mode with time limit conflict
    const maxDurationInput = document.querySelector('input[name="max_duration"]');
    if (maxDurationInput && repairModeCheckbox) {
        if (maxDurationInput.value && repairModeCheckbox.checked) {
            repairModeCheckbox.checked = false;
            showNotification('Repair mode disabled - cannot be used with time limits', 'warning');
        }
    }
}

// Toggle advanced options
function toggleAdvancedOptions() {
    const options = document.getElementById('advanced-options');
    const chevron = document.getElementById('advanced-chevron');
    
    if (options.classList.contains('hidden')) {
        options.classList.remove('hidden');
        chevron.classList.add('rotate-90');
    } else {
        options.classList.add('hidden');
        chevron.classList.remove('rotate-90');
    }
}

// Toggle custom check options based on policy selection
function toggleCustomCheckOptions() {
    const policySelect = document.getElementById('check-policy-select');
    const customOptions = document.getElementById('custom-check-options');
    
    if (policySelect.value === '') {
        customOptions.style.display = 'block';
    } else {
        customOptions.style.display = 'none';
    }
}

// Edit check policy
function editCheckPolicy(policyId) {
    // TODO: Implement edit functionality
    showNotification('Edit functionality coming soon', 'info');
}

// Delete check policy
async function deleteCheckPolicy(policyId) {
    if (!confirm('Are you sure you want to delete this check policy?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/repository-check-configs/${policyId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Check policy deleted successfully', 'success');
            loadCheckPolicies(); // Refresh the list
        } else {
            showNotification('Failed to delete check policy', 'error');
        }
    } catch (error) {
        console.error('Error deleting check policy:', error);
        showNotification('Error deleting check policy', 'error');
    }
}

// Toggle check policy enabled/disabled
async function toggleCheckPolicy(policyId) {
    try {
        const checkbox = event.target;
        const response = await fetch(`/api/repository-check-configs/${policyId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                enabled: checkbox.checked
            })
        });
        
        if (response.ok) {
            showNotification(`Check policy ${checkbox.checked ? 'enabled' : 'disabled'}`, 'success');
            loadCheckPolicies(); // Refresh to update policy select dropdown
        } else {
            checkbox.checked = !checkbox.checked; // Revert on error
            showNotification('Failed to update check policy', 'error');
        }
    } catch (error) {
        console.error('Error updating check policy:', error);
        checkbox.checked = !checkbox.checked; // Revert on error
        showNotification('Error updating check policy', 'error');
    }
}

// Load check history
async function loadCheckHistory() {
    const container = document.getElementById('check-history');
    if (!container) return;
    
    try {
        const response = await fetch('/api/jobs?type=check&limit=5');
        if (response.ok) {
            const jobs = await response.json();
            displayCheckHistory(jobs);
        } else {
            container.innerHTML = `
                <div class="text-center py-4">
                    <p class="text-gray-500">Failed to load check history</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading check history:', error);
        container.innerHTML = `
            <div class="text-center py-4">
                <p class="text-gray-500">Error loading check history</p>
            </div>
        `;
    }
}

// Display check history
function displayCheckHistory(jobs) {
    const container = document.getElementById('check-history');
    if (!container) return;
    
    if (jobs.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4">
                <p class="text-gray-500">No recent checks found</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = jobs.map(job => `
        <div class="border-b border-gray-200 pb-3 mb-3 last:border-b-0">
            <div class="flex items-center justify-between">
                <div>
                    <span class="font-medium text-gray-900">Repository Check</span>
                    <span class="text-sm text-gray-500 ml-2">(ID: ${job.id})</span>
                </div>
                <span class="px-2 py-1 text-xs rounded-full ${getStatusColor(job.status)}">${job.status}</span>
            </div>
            <p class="text-sm text-gray-600 mt-1">${formatDateTime(job.created_at)}</p>
            ${job.result ? `<p class="text-xs text-gray-500 mt-1">${job.result.substring(0, 100)}...</p>` : ''}
        </div>
    `).join('');
}

// Helper function to get status color classes
function getStatusColor(status) {
    switch (status) {
        case 'completed':
            return 'bg-green-100 text-green-800';
        case 'running':
            return 'bg-blue-100 text-blue-800';
        case 'failed':
            return 'bg-red-100 text-red-800';
        case 'pending':
            return 'bg-yellow-100 text-yellow-800';
        default:
            return 'bg-gray-100 text-gray-800';
    }
}

// Helper function to format date and time
function formatDateTime(dateString) {
    try {
        if (!dateString) return 'N/A';
        
        const date = new Date(dateString);
        if (isNaN(date.getTime())) {
            // Try parsing as ISO string if direct parsing fails
            const isoDate = new Date(dateString.replace(' ', 'T'));
            if (isNaN(isoDate.getTime())) {
                return dateString;
            }
            return isoDate.toLocaleDateString() + ' ' + isoDate.toLocaleTimeString();
        }
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    } catch (error) {
        return dateString;
    }
}

// Add event listeners when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Initialize when repository check tab is shown
    if (document.getElementById('tab-repository-check')) {
        // Set up form validation
        const form = document.getElementById('check-policy-form');
        if (form) {
            form.addEventListener('change', updateCheckOptions);
        }
        
        // Initialize custom check options toggle
        toggleCustomCheckOptions();
    }
});