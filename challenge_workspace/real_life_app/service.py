from typing import Optional
from .models import Order

class ECommerceService:
    def __init__(self, repository):
        self.repository = repository

    async def place_order(self, user_id: int, item_id: int, quantity: int) -> Optional[Order]:
        async with self.repository.transaction():
            user = await self.repository.get_user(user_id)
            item = await self.repository.get_item(item_id)
            
            if not user or not item:
                raise ValueError("User or Item not found")
                
            total_price = item.price * quantity
            
            if item.stock < quantity:
                raise ValueError("Out of stock")
                
            if user.balance < total_price:
                raise ValueError("Insufficient balance")
                
            # Deduct user balance
            await self.repository.update_user_balance(user_id, user.balance - total_price)
            
            # Decrement stock
            await self.repository.update_item_stock(item_id, item.stock - quantity)
            
            # Create order
            order = Order(id=None, user_id=user_id, item_id=item_id, quantity=quantity, total_price=total_price)
            created_order = await self.repository.create_order(order)
            
            return created_order