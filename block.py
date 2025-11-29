from dataclasses import dataclass, asdict
import random, string
import hashlib

@dataclass
class Transaction:
    sender_id: str
    receiver_id: str
    amount: int

@dataclass
class Block_Json:
    """JSON-serializable representation of a Block"""
    sender_id: str
    receiver_id: str
    amount: int
    hash_pointer: str
    nonce: str
    hash_result: str
    
    @classmethod
    def from_block(cls, block: 'Block') -> 'Block_Json':
        """Convert Block to Block_Json"""
        return cls(
            sender_id=block.transaction.sender_id,
            receiver_id=block.transaction.receiver_id,
            amount=block.transaction.amount,
            hash_pointer=block.hash_pointer,
            nonce=block.nonce,
            hash_result=block.hash_result
        )
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Block_Json':
        """Convert dictionary to Block_Json"""
        return cls(**data) 
    
    def to_block(self, prev_block: 'Block | None') -> 'Block':
        """Convert Block_Json back to Block (restore, don't mine)"""
        txn = Transaction(self.sender_id, self.receiver_id, self.amount)
        return Block._restore_block(
            transaction=txn,
            prev_block=prev_block,
            hash_pointer=self.hash_pointer,
            nonce=self.nonce,
            hash_result=self.hash_result
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

class Block:
    first_block_hash = "0" * 64
    
    @classmethod
    def _restore_block(cls, transaction: Transaction, prev_block: 'Block | None',
                      hash_pointer: str, nonce: str, hash_result: str) -> 'Block':
        """Helper to restore a single block"""
        block = cls.__new__(cls)
        block.transaction = transaction
        block.prev_block = prev_block
        block.hash_pointer = hash_pointer
        block.nonce = nonce  
        block.hash_result = hash_result
        return block
    
    @classmethod
    def blockchain_from_json(cls, blockchain_dict: dict) -> 'Block | None':
        """Get a dict and turn it into blockchain. Return tail"""
        if not blockchain_dict:
            return None
        
        blockchain_list = blockchain_dict.get("blockchain")
        if not blockchain_list:
            return None
        
        current: Block | None = None
        
        for block_dict in blockchain_list:
            block_json = Block_Json.from_dict(block_dict)
            block = block_json.to_block(current)
            current = block
        
        return current
    
    def __init__(self, transaction: Transaction, prev_block: 'Block | None') -> None:
        self.transaction = transaction
        self.prev_block = prev_block
        self.hash_pointer = self.generate_hash()
        self.nonce, self.hash_result = self.generate_nonce()
    
    def generate_hash(self) -> str:
        if not self.prev_block:
            return self.first_block_hash
        
        data = (str(self.prev_block.transaction) + 
                self.prev_block.hash_pointer + 
                self.prev_block.nonce)
        return hashlib.sha256(data.encode()).hexdigest()
    
    def generate_nonce(self) -> tuple[str, str]:
        while True:  
            nonce = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            data = str(self.transaction) + nonce
            hash_result = hashlib.sha256(data.encode()).hexdigest()
            
            if hash_result[-1] in '01234':
                return (nonce, hash_result)
    
    def to_json(self) -> dict:
        """Convert this entire blockchain to dictionary appropriate for JSON"""
        blocks_list = []
        current = self
        
        while current is not None:
            # Use Block_Json for consistency!
            block_json = Block_Json.from_block(current)
            blocks_list.append(block_json.to_dict())
            current = current.prev_block
        
        blocks_list.reverse()
        return {"blockchain": blocks_list}
    
    def __str__(self) -> str:
        """Print block info"""
        return (
            f"{self.transaction}\n"
            f"prev_block's address: {id(self.prev_block)}\n"
            f"hash_pointer: {self.hash_pointer}\n"
            f"nonce: {self.nonce}\n"
            f"hash w/ nonce: {self.hash_result}"
        )