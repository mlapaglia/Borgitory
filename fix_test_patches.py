#!/usr/bin/env python3
"""
Script to fix app. references in test patch statements
"""
import re
from pathlib import Path

def fix_patches_in_file(file_path):
    """Fix app. references in patch statements in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace patch statements with app. references
        # Match patterns like 'app.services.something' and 'app.models.something'
        updated_content = re.sub(r"'app\.", "'", content)
        updated_content = re.sub(r'"app\.', '"', updated_content)
        
        # Only write if content changed
        if updated_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print(f"Updated: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def main():
    """Update all test files"""
    test_dir = Path('tests')
    updated_count = 0
    
    # Find all Python test files
    for py_file in test_dir.rglob('*.py'):
        if fix_patches_in_file(py_file):
            updated_count += 1
    
    print(f"Updated {updated_count} test files")

if __name__ == '__main__':
    main()
