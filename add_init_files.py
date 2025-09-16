#!/usr/bin/env python3
"""
Script to add __init__.py files to all directories in the src folder.
This makes the src directory a proper Python package structure.
"""

import os
from pathlib import Path


def add_init_files(base_dir: str = "src"):
    """Add __init__.py files to all directories under base_dir that don't have them."""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"Error: Directory '{base_dir}' does not exist")
        return
    
    added_count = 0
    skipped_count = 0
    
    # Walk through all directories
    for root, dirs, files in os.walk(base_path):
        root_path = Path(root)
        init_file = root_path / "__init__.py"
        
        # Skip __pycache__ directories
        if "__pycache__" in str(root_path):
            continue
            
        # Check if __init__.py already exists
        if init_file.exists():
            print(f"✓ Already exists: {init_file}")
            skipped_count += 1
        else:
            # Create empty __init__.py file
            init_file.touch()
            print(f"+ Created: {init_file}")
            added_count += 1
    
    print(f"\nSummary:")
    print(f"  Created: {added_count} __init__.py files")
    print(f"  Skipped: {skipped_count} existing files")
    print(f"  Total directories processed: {added_count + skipped_count}")


if __name__ == "__main__":
    print("Adding __init__.py files to src directory structure...")
    print("=" * 50)
    add_init_files()
