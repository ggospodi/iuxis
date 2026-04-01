#!/usr/bin/env python3
"""
Standalone file watcher runner.
Use this to test the watcher without starting the full FastAPI server.

Usage:
    cd ~/Desktop/iuxis
    python3 scripts/run_file_watcher.py
"""

import logging
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

def main():
    from iuxis.connectors.file_watcher import FileWatcherConnector, INBOX_DIR

    print(f"\n{'='*50}")
    print("Iuxis File Watcher — Standalone Mode")
    print(f"Watching: {INBOX_DIR}")
    print(f"Drop .md, .txt, or .pdf files to trigger ingestion")
    print(f"Press Ctrl+C to stop")
    print(f"{'='*50}\n")

    watcher = FileWatcherConnector()

    # Process any existing files first
    results = watcher.process_inbox_now()
    if results:
        print(f"Processed {len(results)} existing files on startup")

    watcher.start()

    def shutdown(sig, frame):
        print("\nShutting down file watcher...")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
