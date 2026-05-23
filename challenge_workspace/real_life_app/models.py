from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    username: str
    balance: float
    is_active: bool = True

@dataclass
class Item:
    id: int
    name: str
    price: float
    stock: int

@dataclass
class Order:
    id: Optional[int]
    user_id: int
    item_id: int
    quantity: int
    total_price: float
