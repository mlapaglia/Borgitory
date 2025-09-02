#!/usr/bin/env python3
"""
Database reset utility for Borgitory

This script will completely reset the database, removing all data.
Use this if you encounter schema migration issues during development.

Usage: python reset_db.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.database import reset_db

if __name__ == "__main__":
    print("⚠️  WARNING: This will delete ALL data in the database!")
    confirm = input("Are you sure you want to proceed? Type 'yes' to continue: ")
    
    if confirm.lower() == 'yes':
        try:
            reset_db()
            print("🎉 Database has been reset successfully!")
            print("You can now restart the application.")
        except Exception as e:
            print(f"❌ Error resetting database: {e}")
            sys.exit(1)
    else:
        print("❌ Database reset cancelled.")