// Core Alpine.js App Component
function borgitoryApp() {
    return {
        cloudSyncConfigs: [],
        notificationConfigs: [],
        cleanupConfigs: [],
        checkConfigs: [],
        
        initApp() {
        },
    };
}

// HTMX Event Listeners
document.body.addEventListener('htmx:afterSwap', function(e) {
    // Chart initialization is now handled by inline scripts in templates
});

// Dark Mode Functions
function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    if (isDark) {
        html.classList.remove('dark');
        localStorage.setItem('darkMode', 'false');
    } else {
        html.classList.add('dark');
        localStorage.setItem('darkMode', 'true');
    }
}

function initializeDarkMode() {
    const savedMode = localStorage.getItem('darkMode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedMode === 'true' || (savedMode === null && prefersDark)) {
        document.documentElement.classList.add('dark');
    }
}

// Initialize dark mode on page load
document.addEventListener('DOMContentLoaded', initializeDarkMode);