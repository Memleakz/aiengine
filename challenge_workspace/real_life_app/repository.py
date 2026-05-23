import sqlite3
import asyncio
from typing import List, Optional
from contextlib import asynccontextmanager
from .models import User, Item, Order

class SQLiteRepository:
    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

    async def init_db(self):
        def _init():
            with self.connection:
                self.connection.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT,
                        balance REAL,
                        is_active BOOLEAN DEFAULT 1
                    )
                """)
                self.connection.execute("""
                    CREATE TABLE IF not EXISTS items (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        price REAL,
                        stock INTEGER
                    )
                """)
                self.connection.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        item_id INTEGER,
                        quantity INTEGER,
                        total_price REAL,
                        FOREIGN KEY(user_id) REFERENCES users(id),
                        FOREIGN KEY(item_id) REFERENCES items(id)
                    )
                """)
                # Seed users
                self.connection.execute("DELETE FROM users")
                self.connection.execute("INSERT INTO users (id, username, balance) VALUES (1, 'alice', 100.0)")
                self.connection.execute("INSERT INTO users (id, username, balance) VALUES (2, 'bob', 20.0)")
                
                # Seed items
                self.connection.execute("DELETE FROM items")
                self.connection.execute("INSERT INTO items (id, name, price, stock) VALUES (101, 'Coffee Maker', 49.99, 5)")
                self.connection.execute("INSERT INTO items (id, name, price, stock) VALUES (102, 'Coffee Beans', 12.50, 20)")
        
        await asyncio.to_thread(_init)

    @asynccontextmanager
    async def transaction(self):
        def _transaction():
            self.connection.execute("BEGIN")
            return self.connection

        # We need to run the block in a thread if we want to be safe with the connection, 
        # but since we are using check_same_thread=False, we can use the connection directly.
        # However, we need to handle commit/rollback.
        try:
            await asyncio.to_thread(lambda: self.connection.execute("BEGIN"))
            yield self.connection
            await asyncio.to_thread(self.connection.commit)
        except Exception as e:
            await asyncio.to_thread(self.connection.rollback)
            raise e

    async def get_user(self, user_id: int) -> Optional[User]:
        def _get():
            cursor = self.connection.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return User(id=row['id'], username=row['username'], balance=row['balance'], is_active=bool(row['is_active']))
            return None
        return await asyncio.to_thread(_get)

    async def update_user_balance(self, user_id: int, new_balance: float) -> bool:
        def _update():
            cursor = self.connection.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
            return cursor.rowcount > 0
        return await asyncio.to_thread(_update)

    async def get_item(self, item_id: int) -> Optional[Item]:
        def _get():
            cursor = self.connection.execute("SELECT * FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if row:
                return Item(id=row['id'], name=row['name'], price=row['price'], stock=row['stock'])
            return None
        return await asyncio.to_thread(_get)

    async def update_item_stock(self, item_id: int, new_stock: int) -> bool:
        def _update():
            cursor = self.connection.execute("UPDATE items SET stock = ? WHERE id = ?", (new_stock, item_id))
            return cursor.rowcount > 0
        return await asyncio.to_thread(_update)

    async def create_order(self, order: Order) -> Order:
        def _create():
            cursor = self.connection.execute(
                "INSERT INTO orders (user_id, item_id, quantity, total_price) VALUES (?, ?, ?, ?)",
                (order.user_id, order.item_id, order.quantity, order.total_price)
            )
            order.id = cursor.lastrowid
            return order
        return await asyncio.to_thread(_create)

    async def get_orders_by_user(self, user_id: int) -> List[Order]:
        def _get():
            cursor = self.connection.execute(
                "SELECT o.id, o.user_id, o.item_id, o.quantity, o.total_price, i.name, i.price, i.stock "
                "FROM orders o JOIN items i ON o.item_id = i.id WHERE o.user_id = ?", 
                (user_id,)
            )
            rows = cursor.fetchall()
            return [
                Order(id=row['id'], user_id=row['user_id'], item_id=row['item_id'], quantity=row['quantity'], total_price=row['total_price'])
                for row in rows
            ]
        return await asyncio.to_thread(_get)