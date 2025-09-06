#!/usr/bin/env python3
"""
Development server runner for Borgitory
"""
import os
import sys
import subprocess
import uvicorn
from dotenv import load_dotenv

def run_migrations():
    """Run database migrations before starting the app"""
    print("Running database migrations...")
    
    try:
        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True
        )
        print("Database migrations completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print("Database migration failed!")
        print(f"Error: {e}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Alembic command not found!")
        print("Make sure you're running from the correct directory and alembic is installed")
        return False

if __name__ == "__main__":
    load_dotenv()
    
    # Run migrations first
    if not run_migrations():
        print("Exiting due to migration failure")
        sys.exit(1)
    
    print("Starting Borgitory development server on port 8000")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )