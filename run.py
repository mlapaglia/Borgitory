#!/usr/bin/env python3
"""
Development server runner for Borgitory
"""

import sys
import os
import uvicorn
from dotenv import load_dotenv

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


if __name__ == "__main__":
    load_dotenv()

    print("Starting Borgitory development server on port 8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
