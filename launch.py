#!/usr/bin/env python3
"""
Simple launcher for the Document Analyzer application.
"""

import subprocess
import sys
import os

def main():
    """Launch the application using the correct module syntax."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Change to the script directory
    os.chdir(script_dir)
    
    # Run the app.main module
    try:
        subprocess.run([sys.executable, "-m", "app.main"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running application: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
        sys.exit(0)

if __name__ == "__main__":
    main() 