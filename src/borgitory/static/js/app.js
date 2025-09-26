// Notification Management Functions
function createAutoHideNotification(element, timeout = 5000) {
    setTimeout(() => {
        element.style.transition = 'opacity 0.3s ease-in';
        element.style.opacity = '0';
        setTimeout(() => element.remove(), 300);
    }, timeout);
}

function addCloseButton(element) {
    const closeBtn = element.querySelector('[data-close]');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            element.style.transition = 'opacity 0.3s ease-in';
            element.style.opacity = '0';
            setTimeout(() => element.remove(), 300);
        });
    }
}

function initializeNotifications() {
    // Initialize auto-hide notifications
    document.querySelectorAll('[data-auto-hide]').forEach(el => {
        const timeout = parseInt(el.dataset.autoHide) || 5000;
        createAutoHideNotification(el, timeout);
        addCloseButton(el);
    });
}

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

// Initialize dark mode and notifications on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeDarkMode();
    initializeNotifications();
});

// Handle HTMX-loaded content
document.addEventListener('htmx:afterSwap', function(e) {
    // Initialize notifications in newly loaded content
    e.target.querySelectorAll('[data-auto-hide]').forEach(el => {
        const timeout = parseInt(el.dataset.autoHide) || 5000;
        createAutoHideNotification(el, timeout);
        addCloseButton(el);
    });
});