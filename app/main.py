#!/usr/bin/env python3

# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
Entry point wrapper for the E-Series Performance collector.
This is a simple wrapper that redirects to the main collector.
For full functionality, use collector.py directly.
"""

if __name__ == "__main__":
    import sys
    import subprocess
    
    print("Note: main.py is a wrapper for collector.py")
    print("Redirecting to the full-featured collector...")
    print()
    
    # Pass all arguments to collector.py
    collector_args = [sys.executable, "app/collector.py"] + sys.argv[1:]
    
    try:
        # Execute collector.py with the same arguments
        result = subprocess.run(collector_args, check=False)
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("Error: Could not find app/collector.py")
        print("Please run from the project root directory:")
        print("python3 app/collector.py [options]")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCollection interrupted by user")
        sys.exit(0)
