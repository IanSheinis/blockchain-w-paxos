from dataclasses import dataclass, asdict
@dataclass
class Transaction:
    sender_id: str
    receiver_id: str
    amount: int

class enum_transaction():
