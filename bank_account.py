from block import Block, Transaction
class Bank_Account:
    balances: dict
    def __init__(self) -> None:
        self.balances = {
            "P1": 100.0,
            "P2": 100.0,
            "P3": 100.0,
            "P4": 100.0,
            "P5": 100.0
        }

    def transfer(self, block: Block):
        """
        Executes transaction
        """
        transaction: Transaction = block.transaction

        sender = transaction.sender_id
        receiver = transaction.receiver_id
        amount = transaction.amount
        
        # Validation
        if self.balances[sender] < amount:
            raise ValueError(
                f"Insufficient balance! {sender} has ${self.balances[sender]}, "
                f"needs ${amount}"
            )
        
        # Execute transfer
        self.balances[sender] -= amount
        self.balances[receiver] += amount

    def get_balance(self, node_id: str) -> float:
        """
        Get balance for a node
        """
        return self.balances[node_id]