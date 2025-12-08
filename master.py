#!/usr/bin/env python3
"""
Master process - sends commands to blockchain nodes
Run with: python master.py
"""
import asyncio
import sys
from transaction import master
async def main():
    m = master()
   
    print("="*60)
    print("Blockchain Master Interface")
    print("="*60)
    print("\nCommands:")
    print(" transfer <from> <to> <amount> - Transfer money")
    print(" balance - Print balance for all 5 processes")
    print(" blockchain <process> - Print blockchain")
    print(" fail <process> - Fail a process")
    print(" fix <process> - Fix a process")
    print(" queue <process> - Print queue for process")
    print(" queue_start <process> - Start queue for process")
    print(" queue_delete <process> - Delete queue for process")
    print(" quit - Exit")
    print("\nExample: transfer P1 P2 50")
    print("="*60 + "\n")
   
    while True:
        try:
            # Get user input
            cmd = input("master> ").strip()
           
            if not cmd:
                continue
           
            parts = cmd.split()
            command = parts[0].lower()
           
            # Handle commands
            if command == "quit" or command == "exit":
                print("Exiting...")
                break
           
            elif command == "transfer":
                if len(parts) != 4:
                    print("Usage: transfer <from> <to> <amount>")
                    continue
               
                from_node = parts[1].upper()
                to_node = parts[2].upper()
               
                try:
                    amount = int(parts[3])
                except ValueError:
                    print("Error: amount must be a number")
                    continue
               
                print(f"\nSending transaction: {from_node} → {to_node} ${amount}")
                await m.moneyTransfer(from_node, to_node, amount)
                print("Transaction sent!\n")
           
            elif command == "balance":
                if len(parts) != 1:
                    print("Usage: balance")
                    continue
               
                print(f"\nRequesting balance from all processes...")
                await m.printBalance()
                print()
           
            elif command == "blockchain":
                if len(parts) != 2:
                    print("Usage: blockchain <process>")
                    continue
               
                process = parts[1].upper()
                print(f"\nRequesting blockchain from {process}...")
                await m.printBlockchain(process)
                print()
           
            elif command == "fail":
                if len(parts) != 2:
                    print("Usage: fail <process>")
                    continue
               
                process = parts[1].upper()
                print(f"\nFailing process {process}...")
                await m.fail_process(process)
                print()
           
            elif command == "fix":
                if len(parts) != 2:
                    print("Usage: fix <process>")
                    continue
               
                process = parts[1].upper()
                print(f"\nFixing process {process}...")
                await m.fix_process(process)
                print()

            elif command == "queue":
                if len(parts) != 2:
                    print("Usage: queue <process>")
                    continue
               
                process = parts[1].upper()
                print(f"\nRequesting queue from {process}...")
                await m.queue(process)
                print()

            elif command == "queue_start":
                if len(parts) != 2:
                    print("Usage: queue_start <process>")
                    continue
               
                process = parts[1].upper()
                print(f"\nStarting queue for {process}...")
                await m.queue_start(process)
                print()

            elif command == "queue_delete":
                if len(parts) != 2:
                    print("Usage: queue_delete <process>")
                    continue
               
                process = parts[1].upper()
                print(f"\nDeleting queue for {process}...")
                await m.queue_delete(process)
                print()
           
            else:
                print(f"Unknown command: {command}")
                print("Type 'quit' to exit")
       
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
       
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        sys.exit(0)