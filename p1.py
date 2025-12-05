# simple_test_p1.py

from block import Block, Transaction
from bank_account import Bank_Account

FILE_NAME = "p1.json"

# Create blockchain
print("Creating blockchain...")
b1 = Block(Transaction("P1", "P2", 50), None)
b2 = Block(Transaction("P2", "P3", 25), b1)
b3 = Block(Transaction("P3", "P1", 10), b2)

# Show bank accounts
print("\nOriginal bank accounts:")
bank = Bank_Account(b3)
bank.print_balances()

# Save
print("\nSaving to p1.json...")
b3.write_to_json(FILE_NAME)

# Load
print("\nLoading from p1.json...")
tail = Block.load_from_json(FILE_NAME)
if not tail:
    raise ValueError("tail is None")

# Rebuild bank accounts
print("\nRebuilt bank accounts:")
bank2 = Bank_Account(tail)
bank2.print_balances()

# Verify
print("\nVerification:")
print(f"Nonces match: {b3.nonce == tail.nonce}")
print(f"P1 balance match: {bank.get_balance('P1') == bank2.get_balance('P1')}")
print(f"b3 length {b3.length()}")