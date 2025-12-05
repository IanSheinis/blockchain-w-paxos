import config
from dataclasses import dataclass, asdict
import random, string
import hashlib
import json

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
    def from_block(cls, block: Block) -> Block_Json:
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
    def from_dict(cls, data: dict) -> Block_Json:
        """Convert dictionary to Block_Json"""
        return cls(**data) 
    
    def to_block(self, prev_block: Block | None) -> Block:
        """Convert Block_Json back to Block (restore, dont mine)"""
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
    @classmethod
    def _restore_block(cls, transaction: Transaction, prev_block: Block | None,
                      hash_pointer: str, nonce: str, hash_result: str) -> Block:
        """Helper to restore a single block"""
        block = cls.__new__(cls)
        block.transaction = transaction
        block.prev_block = prev_block
        block.hash_pointer = hash_pointer
        block.nonce = nonce  
        block.hash_result = hash_result
        return block
    
    @classmethod
    def _blockchain_from_json(cls, blockchain_dict: dict) -> Block | None:
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
    
    @classmethod
    def load_from_json(cls, filename: str) -> Block | None:
        """Load blockchain from JSON file"""
        if filename not in config.CORRECT_FILE_NAMES:
            raise ValueError(f"Filename must be one of: p1.json, p2.json, p3.json, p4.json, p5.json. Got: {filename}")
    
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
        
            tail = cls._blockchain_from_json(data)
        
            if tail:
                print(f"✓ Loaded {len(data['blockchain'])} blocks from {filename}")
        
            return tail
        
        except FileNotFoundError:
            print(f"⚠️ {filename} not found")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON in {filename}: {e}")
            return None

    def write_to_json(self, filename: str):
        """Write blockchain to JSON file"""
        if filename not in config.CORRECT_FILE_NAMES:
            raise ValueError(f"Filename must be one of: p1.json, p2.json, p3.json, p4.json, p5.json. Got: {filename}")
    
        data = self.to_json()
    
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"✓ Blockchain saved to {filename}")
    
    def __init__(self, transaction: Transaction, prev_block: Block | None) -> None:
        self.transaction = transaction
        self.prev_block = prev_block
        self.hash_pointer = self.generate_hash()
        self.nonce, self.hash_result = self.generate_nonce()
        # Print when block is created
        print(f'\n☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐\nCreated block:\n{self}\n☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐☐\n')

    def generate_hash(self) -> str:
        if not self.prev_block:
            return config.FIRST_BLOCK_HASH
        
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
            block_json = Block_Json.from_block(current)
            blocks_list.append(block_json.to_dict())
            current = current.prev_block
        
        blocks_list.reverse()
        return {"blockchain": blocks_list}
    
    def print_blockchain(self):
        """Print blockchain in readable JSON format"""
        data = self.to_json()
        print(json.dumps(data, indent=2))

    def length(self):
        length = 0
        current = self
        while current:
            length += 1
            current = current.prev_block
        return length
    
    def __str__(self) -> str:
        """Print block info"""
        return (
            f"{self.transaction}\n"
            f"prev_block's address: {id(self.prev_block)}\n"
            f"hash_pointer: {self.hash_pointer}\n"
            f"nonce: {self.nonce}\n"
            f"hash w/ nonce: {self.hash_result}"
        )
    