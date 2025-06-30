#!/usr/bin/env python3
"""
Entry point for the Document Analyzer application.
Run this file to start the application.
"""

import sys
import os

# Add the current directory to Python path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main application
from app.main import main_page

if __name__ == "__main__":
    # The main.py file already has ui.run() at the bottom, so we just need to import it
    pass 