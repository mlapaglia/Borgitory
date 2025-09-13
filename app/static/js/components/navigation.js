// Navigation utilities for HTMX-based tabs
// Most navigation is now handled by HTMX, but we keep utility functions for mobile sidebar

// Mobile sidebar management for HTMX navigation
window.htmxCloseMobileSidebar = function() {
    if (window.innerWidth < 1024) {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        const hamburger = document.getElementById('hamburger-icon');
        const closeIcon = document.getElementById('close-icon');
        const menuButton = document.getElementById('mobile-menu-button');

        // Only manipulate elements that exist
        if (sidebar) {
            sidebar.classList.remove('mobile-open');
        }
        if (overlay) {
            overlay.classList.add('hidden');
            overlay.classList.remove('show');
        }
        if (hamburger) {
            hamburger.classList.remove('hidden');
        }
        if (closeIcon) {
            closeIcon.classList.add('hidden');
        }
        if (menuButton) {
            menuButton.setAttribute('aria-expanded', 'false');
        }

        // Safe DOM manipulation
        if (document.body) {
            document.body.classList.remove('mobile-sidebar-open');
        }
    }
}

// Auto-close mobile sidebar after HTMX navigation
document.addEventListener('htmx:afterSwap', function(e) {
    if (e.target && e.target.id === 'main-content') {
        htmxCloseMobileSidebar();
    }
});