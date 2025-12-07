#!/usr/bin/env python3
"""
Process P4 - Blockchain node
Run with: python p4.py
"""

import asyncio
import sys
from paxos import paxos

async def main():
    # Create paxos node for P4
    process_name = "P4"
    node = paxos(process_name)
    
    print(f"{'='*60}")
    print(f"Starting Process {process_name}")
    print(f"{'='*60}\n")
    
    # Start the server (so it can receive messages)
    await node.start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutting down P4...")
        sys.exit(0)