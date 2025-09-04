// Core Alpine.js App Component
function borgitoryApp() {
    return {
        selectedRepository: null,
        repositories: [],
        cloudSyncConfigs: [],
        notificationConfigs: [],
        cleanupConfigs: [],
        checkConfigs: [],
        
        init() {
            this.loadRepositories();
            this.loadCloudSyncConfigs();
            this.loadNotificationConfigs();
            this.loadCleanupConfigs();
            this.loadCheckConfigs();
            loadJobHistory(); // Load initial job history
            initializeSSE(); // Set up single SSE connection
            initializeTabs(); // Initialize tabs
            // Store instance globally for form handler
            window.borgitoryAppInstance = this;
        },
        
        async loadRepositories() {
            try {
                const response = await fetch('/api/repositories/');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                this.repositories = await response.json();
                this.updateRepositorySelect();
            } catch (error) {
                showNotification('Failed to load repositories: ' + error.message, 'error');
            }
        },

        async loadCloudSyncConfigs() {
            try {
                const response = await fetch('/api/cloud-sync/');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                this.cloudSyncConfigs = await response.json();
                this.updateCloudSyncSelects();
            } catch (error) {
                console.error('Failed to load cloud sync configs:', error);
            }
        },

        async loadNotificationConfigs() {
            try {
                const response = await fetch('/api/notifications/');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                this.notificationConfigs = await response.json();
                this.updateNotificationSelects();
            } catch (error) {
                console.error('Failed to load notification configs:', error);
            }
        },

        async loadCleanupConfigs() {
            try {
                const response = await fetch('/api/cleanup/');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                this.cleanupConfigs = await response.json();
                this.updateCleanupSelects();
            } catch (error) {
                console.error('Failed to load cleanup configs:', error);
            }
        },

        async loadCheckConfigs() {
            try {
                const response = await fetch('/api/repository-check-configs/');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                this.checkConfigs = await response.json();
                this.updateCheckSelects();
            } catch (error) {
                console.error('Failed to load check configs:', error);
            }
        },
        
        updateRepositorySelect() {
            const selects = document.querySelectorAll('select[name="repository_id"]');
            selects.forEach(select => {
                select.innerHTML = '<option value="">Select Repository...</option>';
                this.repositories.forEach(repo => {
                    const option = document.createElement('option');
                    option.value = repo.id;
                    option.textContent = repo.name;
                    select.appendChild(option);
                });
            });
            
            // Update archive repository select if on archives tab
            populateArchiveRepositorySelect();
            
            // Also update the repository list display
            this.updateRepositoryList();
        },
        
        updateRepositoryList() {
            // This will be handled by HTMX
        },

        updateCloudSyncSelects() {
            const selects = document.querySelectorAll('#backup-cloud-select, #schedule-cloud-select');
            selects.forEach(select => {
                // Keep the "No cloud sync" option
                const defaultOption = select.querySelector('option[value=""]');
                select.innerHTML = '';
                select.appendChild(defaultOption);
                
                // Add cloud sync config options
                this.cloudSyncConfigs.forEach(config => {
                    if (config.enabled) { // Only show enabled configs
                        const option = document.createElement('option');
                        option.value = config.id;
                        option.textContent = `${config.name} (${config.bucket_name || config.host || config.provider})`;
                        select.appendChild(option);
                    }
                });
            });
        },

        updateNotificationSelects() {
            const selects = document.querySelectorAll('#backup-notification-select, #schedule-notification-select');
            selects.forEach(select => {
                // Keep the "No notifications" option
                const defaultOption = select.querySelector('option[value=""]');
                select.innerHTML = '';
                select.appendChild(defaultOption);
                
                // Add notification config options
                this.notificationConfigs.forEach(config => {
                    if (config.enabled) { // Only show enabled configs
                        const option = document.createElement('option');
                        option.value = config.id;
                        const notifyTypes = [];
                        if (config.notify_on_success) notifyTypes.push('✅');
                        if (config.notify_on_failure) notifyTypes.push('❌');
                        option.textContent = `${config.name} (${notifyTypes.join('')})`;
                        select.appendChild(option);
                    }
                });
            });
        },

        updateCleanupSelects() {
            const selects = document.querySelectorAll('#backup-cleanup-select, #schedule-cleanup-select');
            selects.forEach(select => {
                // Keep the "No cleanup" option
                const defaultOption = select.querySelector('option[value=""]');
                select.innerHTML = '';
                select.appendChild(defaultOption);
                
                // Add cleanup config options
                this.cleanupConfigs.forEach(config => {
                    if (config.enabled) { // Only show enabled configs
                        const option = document.createElement('option');
                        option.value = config.id;
                        let description = config.name;
                        if (config.strategy === 'simple' && config.keep_within_days) {
                            description += ` (${config.keep_within_days} days)`;
                        } else if (config.strategy === 'advanced') {
                            const parts = [];
                            if (config.keep_daily) parts.push(`${config.keep_daily}d`);
                            if (config.keep_weekly) parts.push(`${config.keep_weekly}w`);
                            if (config.keep_monthly) parts.push(`${config.keep_monthly}m`);
                            if (config.keep_yearly) parts.push(`${config.keep_yearly}y`);
                            if (parts.length > 0) description += ` (${parts.join(',')})`;
                        }
                        option.textContent = description;
                        select.appendChild(option);
                    }
                });
            });
        },

        updateCheckSelects() {
            const selects = document.querySelectorAll('#backup-check-select, #schedule-check-select');
            selects.forEach(select => {
                // Keep the "No check" option
                const defaultOption = select.querySelector('option[value=""]');
                select.innerHTML = '';
                select.appendChild(defaultOption);
                
                // Add check config options
                this.checkConfigs.forEach(config => {
                    if (config.enabled) { // Only show enabled configs
                        const option = document.createElement('option');
                        option.value = config.id;
                        let description = config.name;
                        
                        // Add check type information
                        if (config.check_type === 'full') {
                            description += ' (Full)';
                        } else if (config.check_type === 'repository_only') {
                            description += ' (Repo Only)';
                        } else if (config.check_type === 'archives_only') {
                            description += ' (Archives)';
                        }
                        
                        // Add verification indicators
                        const indicators = [];
                        if (config.verify_data) indicators.push('Data Verify');
                        if (config.repair_mode) indicators.push('Repair');
                        if (indicators.length > 0) description += ` [${indicators.join(', ')}]`;
                        
                        option.textContent = description;
                        select.appendChild(option);
                    }
                });
            });
        },

        async deleteRepository(repoId, repoName) {
            if (!confirm(`Are you sure you want to delete the repository "${repoName}"? This action cannot be undone.`)) {
                return;
            }
            
            try {
                const response = await fetch(`/api/repositories/${repoId}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    showNotification(`Repository "${repoName}" deleted successfully!`, 'success');
                    // Reload repositories
                    await this.loadRepositories();
                    // Trigger HTMX refresh for repository list
                    document.body.dispatchEvent(new CustomEvent('repositoryUpdate'));
                    // Refresh schedules panels
                    htmx.ajax('GET', '/api/schedules/html', { target: '#existing-schedules', swap: 'innerHTML' });
                    htmx.ajax('GET', '/api/schedules/upcoming/html', { target: '#upcoming-schedules', swap: 'innerHTML' });
                } else {
                    const error = await response.json();
                    showNotification(`Failed to delete repository: ${error.detail}`, 'error');
                }
            } catch (error) {
                showNotification(`Failed to delete repository: ${error.message}`, 'error');
            }
        }
    };
}

// Chart instances (global scope for updates)
let sizeChart = null;
let ratioChart = null;
let fileTypeCountChart = null;
let fileTypeSizeChart = null;

// Clean HTMX Chart.js Integration
document.body.addEventListener('htmx:afterSwap', function(e) {
    // Check if we swapped in chart data
    if (e.target.id === 'statistics-content' || e.target.querySelector('#chart-data')) {
        const chartDataEl = e.target.querySelector('#chart-data') || document.getElementById('chart-data');
        
        if (chartDataEl && chartDataEl.dataset.sizeChart) {
            try {
                const sizeDataRaw = chartDataEl.getAttribute('data-size-chart');
                const ratioDataRaw = chartDataEl.getAttribute('data-ratio-chart');
                const fileTypeCountDataRaw = chartDataEl.getAttribute('data-file-type-count-chart');
                const fileTypeSizeDataRaw = chartDataEl.getAttribute('data-file-type-size-chart');
                
                const sizeData = JSON.parse(sizeDataRaw);
                const ratioData = JSON.parse(ratioDataRaw);
                const fileTypeCountData = JSON.parse(fileTypeCountDataRaw);
                const fileTypeSizeData = JSON.parse(fileTypeSizeDataRaw);
                
                if (sizeChart && ratioChart && fileTypeCountChart && fileTypeSizeChart) {
                    updateCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData);
                } else {
                    createCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData);
                }
            } catch (error) {
                console.error('Error processing chart data:', error);
            }
        }
    }
});

function createCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData) {
    const sizeCtx = document.getElementById('sizeChart');
    const ratioCtx = document.getElementById('ratioChart');
    const fileTypeCountCtx = document.getElementById('fileTypeCountChart');
    const fileTypeSizeCtx = document.getElementById('fileTypeSizeChart');
    
    if (sizeCtx && ratioCtx) {
        // Create Size Chart
        sizeChart = new Chart(sizeCtx, {
            type: 'line',
            data: sizeData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Size (MB)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Archive Date'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Repository Size Growth'
                    },
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // Create Ratio Chart
        ratioChart = new Chart(ratioCtx, {
            type: 'line',
            data: ratioData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Compression Ratio (%)'
                        },
                        min: 0,
                        max: 100
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Deduplication Ratio (%)'
                        },
                        min: 0,
                        max: 100,
                        grid: {
                            drawOnChartArea: false,
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Archive Date'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Compression & Deduplication Efficiency'
                    },
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
        
        // Create File Type Count Chart
        if (fileTypeCountCtx && fileTypeCountData) {
            fileTypeCountChart = new Chart(fileTypeCountCtx, {
                type: 'line',
                data: fileTypeCountData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'File Count'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Archive Date'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
        }
        
        // Create File Type Size Chart
        if (fileTypeSizeCtx && fileTypeSizeData) {
            fileTypeSizeChart = new Chart(fileTypeSizeCtx, {
                type: 'line',
                data: fileTypeSizeData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Size (MB)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Archive Date'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
        }
    }
}

function updateCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData) {
    if (sizeChart) {
        sizeChart.data = sizeData;
        sizeChart.update('none'); // No animation for smooth updates
    }
    
    if (ratioChart) {
        ratioChart.data = ratioData;
        ratioChart.update('none');
    }
    
    if (fileTypeCountChart && fileTypeCountData) {
        fileTypeCountChart.data = fileTypeCountData;
        fileTypeCountChart.update('none');
    }
    
    if (fileTypeSizeChart && fileTypeSizeData) {
        fileTypeSizeChart.data = fileTypeSizeData;
        fileTypeSizeChart.update('none');
    }
}