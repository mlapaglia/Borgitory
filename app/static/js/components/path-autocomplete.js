// Path Autocomplete Functionality

class PathAutocomplete {
    constructor(inputId, dropdownId) {
        this.input = document.getElementById(inputId);
        this.dropdown = document.getElementById(dropdownId);
        this.currentDirectories = [];
        this.debounceTimer = null;
        this.selectedIndex = -1;
        
        if (this.input && this.dropdown) {
            this.init();
        }
    }
    
    init() {
        this.input.addEventListener('input', (e) => this.handleInput(e));
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.input.addEventListener('blur', (e) => this.handleBlur(e));
        this.input.addEventListener('focus', (e) => this.handleFocus(e));
        
        // Prevent form submission when pressing Enter on dropdown items
        this.dropdown.addEventListener('mousedown', (e) => {
            e.preventDefault();
        });
    }
    
    handleInput(e) {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => {
            this.updateAutocomplete(e.target.value);
        }, 200);
    }
    
    handleKeydown(e) {
        const items = this.dropdown.querySelectorAll('.autocomplete-item');
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
                this.updateSelection(items);
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
                this.updateSelection(items);
                break;
                
            case 'Enter':
                if (this.selectedIndex >= 0 && items[this.selectedIndex]) {
                    e.preventDefault();
                    this.selectItem(items[this.selectedIndex]);
                }
                break;
                
            case 'Escape':
                this.hideDropdown();
                break;
        }
    }
    
    handleBlur(e) {
        // Delay hiding to allow clicks on dropdown items
        setTimeout(() => {
            this.hideDropdown();
        }, 200);
    }
    
    handleFocus(e) {
        if (this.input.value) {
            this.updateAutocomplete(this.input.value);
        }
    }
    
    async updateAutocomplete(value) {
        if (!value || !value.startsWith('/')) {
            this.hideDropdown();
            return;
        }
        
        // Extract the directory path (everything up to the last slash)
        const lastSlashIndex = value.lastIndexOf('/');
        let dirPath, searchTerm;
        
        if (lastSlashIndex === 0) {
            // Input like "/re" - search in root directory for folders starting with "re"
            dirPath = '/';  // Search at root level
            searchTerm = value.substring(1); // Remove leading slash
        } else if (lastSlashIndex > 0) {
            // Input like "/repos/my" - search in "/repos" for folders starting with "my"
            dirPath = value.substring(0, lastSlashIndex);
            searchTerm = value.substring(lastSlashIndex + 1);
        } else {
            // Input like "repos" without leading slash - shouldn't happen with our validation
            dirPath = '/';
            searchTerm = value;
        }
        
        // Security: ensure we only search under /repos or root
        if (dirPath !== '/' && !dirPath.startsWith('/repos')) {
            this.hideDropdown();
            return;
        }
        
        try {
            const url = `/api/repositories/directories?path=${encodeURIComponent(dirPath)}`;
            const response = await fetch(url);
            
            if (response.ok) {
                const data = await response.json();
                this.currentDirectories = data.directories || [];
                this.showDropdown(dirPath, searchTerm);
            } else {
                this.hideDropdown();
            }
        } catch (error) {
            console.error('Error fetching directories:', error);
            this.hideDropdown();
        }
    }
    
    showDropdown(basePath, searchTerm) {
        // Filter directories based on search term
        const filteredDirs = this.currentDirectories.filter(dir => 
            dir.name.toLowerCase().includes(searchTerm.toLowerCase())
        );
        
        if (filteredDirs.length === 0) {
            this.hideDropdown();
            return;
        }
        
        // Build dropdown HTML
        const html = filteredDirs.map(dir => `
            <div class="autocomplete-item px-3 py-2 cursor-pointer hover:bg-gray-100 border-b border-gray-100 last:border-b-0" 
                 data-path="${dir.path}">
                <div class="flex items-center space-x-2">
                    <svg class="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"></path>
                    </svg>
                    <span class="text-sm text-gray-900">${dir.name}</span>
                </div>
                <div class="text-xs text-gray-500 ml-6">${dir.path}</div>
            </div>
        `).join('');
        
        this.dropdown.innerHTML = html;
        this.dropdown.classList.remove('hidden');
        this.selectedIndex = -1;
        
        // Add click handlers
        this.dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => this.selectItem(item));
        });
    }
    
    hideDropdown() {
        this.dropdown.classList.add('hidden');
        this.selectedIndex = -1;
    }
    
    selectItem(item) {
        const path = item.dataset.path;
        this.input.value = path + '/';
        this.hideDropdown();
        this.input.focus();
        
        // Trigger input event to potentially show subdirectories
        setTimeout(() => {
            this.updateAutocomplete(this.input.value);
        }, 100);
    }
    
    updateSelection(items) {
        items.forEach((item, index) => {
            if (index === this.selectedIndex) {
                item.classList.add('bg-blue-100');
            } else {
                item.classList.remove('bg-blue-100');
            }
        });
    }
}

// Initialize path autocomplete for all forms when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Repository Management forms
    new PathAutocomplete('create-path', 'create-path-dropdown');
    new PathAutocomplete('import-path', 'import-path-dropdown');
    
    // Backup form
    new PathAutocomplete('backup-source-path', 'backup-source-path-dropdown');
    
    // Schedule form
    new PathAutocomplete('schedule-source-path', 'schedule-source-path-dropdown');
});