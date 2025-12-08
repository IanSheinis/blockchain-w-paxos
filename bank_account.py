import config
from block import Block, Transaction

class Bank_Account:
    balances: dict
    
    def __init__(self, block: Block | None = None) -> None:
        """
        Initialize bank accounts.
        If block (tail) is provided, rebuild balances from entire blockchain.
        Otherwise, start with default initial balances.
        """
        # "each with a balance starting with $100"
        self.balances = config.INITIAL_BALANCES.copy()  # Use .copy() to avoid reference issues
        
        # If blockchain provided, rebuild from transactions
        if block is not None:
            self._rebuild_from_blockchain(block)
    
    def _rebuild_from_blockchain(self, tail: Block):
        """Rebuild balances by applying all transactions from blockchain"""
        blocks = []
        current = tail
        while current is not None:
            blocks.append(current)
            current = current.prev_block
        
        blocks.reverse()
        
        for block in blocks:
            self.transfer(block)
        
        print(f"✓ Rebuilt balances from {len(blocks)} blocks")

    def transfer(self, block: Block):
        """Execute transaction"""
        transaction: Transaction = block.transaction
        sender = transaction.sender_id
        receiver = transaction.receiver_id
        amount = transaction.amount
        
        # Validation
        if sender not in self.balances:
            raise ValueError(f"Unknown sender: {sender}")
        
        if receiver not in self.balances:
            raise ValueError(f"Unknown receiver: {receiver}")
        
        if self.balances[sender] < amount:
            raise ValueError(
                f"Insufficient balance! {sender} has ${self.balances[sender]:.2f}, "
                f"needs ${amount:.2f}"
            )
        
        # Execute transfer
        self.balances[sender] -= amount
        self.balances[receiver] += amount

    def get_balance(self, node_id: str) -> float:
        """Get balance for a node"""
        balance = self.balances.get(node_id)
        if not balance:
            raise ValueError(f'Tried bankaccount get_balance, no process found of {node_id}')
        return balance
    
    def get_balances_string(self) -> str:
        """Return a string of all account balances (for printBalance command)"""
        result = "\n=== Bank Accounts ===\n"
        for account in sorted(self.balances.keys()):
            balance = self.balances[account]
            result += f"{account}: ${balance:.2f}\n"
        return result

    def print_balances(self) -> None:
        """Print all account balances (for printBalance command)"""
        print("\n=== Bank Accounts ===")
        for account in sorted(self.balances.keys()):
            balance = self.balances[account]
            print(f"{account}: ${balance:.2f}")