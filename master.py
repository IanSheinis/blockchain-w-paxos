#!/usr/bin/env python3
"""
Master process - sends commands to blockchain nodes
Run with: python master.py
"""
import config
import subprocess
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
    print(" balance <process> - Print balance for a single processes")
    print(" balance_all - Print balance for all processes")
    print(" blockchain <process> - Print blockchain")
    print(" fail <process> - Fail a process")
    print(" fix <process> - Fix a process")
    print(" reset_all - Reset all process proposer/acceptors")
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
                if len(parts) != 2:
                    print("Usage: balance <process>")
                    continue
                process = parts[1].upper()
                print(f"\nRequesting balance from all processes...")
                await m.printBalance(process)
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
                if process not in config.CORRECT_PROCESS_NAMES:
                    print(f"Process must be correct name: {process}")
                    continue

                if is_script_running(f'{process.lower()}.py'):
                    print(f"\nProcess {process} is already running")
                    continue
                
                print(f"\nStarting process back up for {process}...")
                subprocess.Popen(
                    f'python -u {process.lower()}.py fix > logs/{process.lower()}.log 2>&1 &',
                    shell=True
                )
                print()

            elif command == "balance_all":
                if len(parts) != 1:
                    print("Usage: balance_all")
                    continue

                print("Requesting balance_all")
                await m.printBalanceAll()
                print()

            elif command == "reset_all":
                if len(parts) != 1:
                    print("Usage: reset_all")
                    continue

                print("Requesting reset_all")
                await m.reset_all()
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

def is_script_running(script_name):
    result = subprocess.run(
        ['pgrep', '-f', script_name],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        sys.exit(0)