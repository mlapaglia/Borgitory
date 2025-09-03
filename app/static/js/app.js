// Core Alpine.js App Component
function borgitoryApp() {
    return {
        selectedRepository: null,
        repositories: [],
        cloudSyncConfigs: [],
        notificationConfigs: [],
        cleanupConfigs: [],
        
        init() {
            this.loadRepositories();
            this.loadCloudSyncConfigs();
            this.loadNotificationConfigs();
            this.loadCleanupConfigs();
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