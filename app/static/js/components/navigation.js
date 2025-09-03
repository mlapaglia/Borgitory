// Tab Navigation
function switchTab(tabName) {
    // Hide all tab content
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => {
        tab.classList.add('hidden');
    });
    
    // Remove active class from all nav items
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    
    // Add active class to selected nav item
    document.getElementById(`nav-${tabName}`).classList.add('active');
    
    // Handle tab-specific initialization
    if (tabName === 'archives') {
        populateArchiveRepositorySelect();
    } else if (tabName === 'debug') {
        loadDebugInfo();
    }
}

// Initialize the first tab as active
function initializeTabs() {
    switchTab('repositories');
}