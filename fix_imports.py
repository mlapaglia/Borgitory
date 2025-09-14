#!/usr/bin/env python3
"""
Script to remove 'src.' prefix from import statements
"""
import re
from pathlib import Path

def fix_imports_in_file(file_path):
    """Remove src. prefix from import statements in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace import statements to remove src. prefix
        updated_content = re.sub(r'from src\.', 'from ', content)
        updated_content = re.sub(r'import src\.', 'import ', updated_content)
        
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
    """Update all Python files in the project"""
    project_root = Path('.')
    updated_count = 0
    
    # Find all Python files
    for py_file in project_root.rglob('*.py'):
        if fix_imports_in_file(py_file):
            updated_count += 1
    
    print(f"Updated {updated_count} files")

if __name__ == '__main__':
    main()
