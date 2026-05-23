import asyncio
import os
import shutil
import sqlite3
import time
import pytest
import sys

# Add challenge_workspace to path so we can import the refactored code
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "challenge_workspace")))

# Try to import the target modules. If they are not fully completed yet, the tests will fail gracefully.
try:
    from real_life_app.models import User, Item, Order
    from real_life_app.repository import SQLiteRepository
    from real_life_app.auth import TokenBucketRateLimiter
    from real_life_app.service import ECommerceService
except ImportError:
    pass


DB_PATH = "test_ecommerce.db"


@pytest.fixture(autouse=True)
def cleanup_db():
    # Remove any test databases before and after each test run
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            pass


# ==============================================================================
# SECTION 1: DATABASE & CRUD TESTING
# ==============================================================================

@pytest.mark.asyncio
async def test_db_initialization():
    """Verify that the repository initializes the SQLite schema and seeds initial data."""
    repo = SQLiteRepository(db_path=DB_PATH)
    await repo.init_db()
    
    assert os.path.exists(DB_PATH), "Database file was not created!"
    
    # Query sqlite directly to verify tables exist
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    assert "users" in tables, "Table 'users' is missing!"
    assert "items" in tables, "Table 'items' is missing!"
    assert "orders" in tables, "Table 'orders' is missing!"
    
    # Check seeded users
    cursor.execute("SELECT id, username, balance FROM users ORDER BY id;")
    users = cursor.fetchall()
    assert len(users) >= 2, "Seeded users are missing!"
    assert users[0][1] == "alice"
    assert users[0][2] == 100.0
    
    # Check seeded items
    cursor.execute("SELECT id, name, price, stock FROM items ORDER BY id;")
    items = cursor.fetchall()
    assert len(items) >= 2, "Seeded items are missing!"
    assert items[0][1] == "Coffee Maker"
    assert items[0][3] == 5
    
    conn.close()


@pytest.mark.asyncio
async def test_db_crud_operations():
    """Verify that user and item queries/updates function correctly in SQLite."""
    repo = SQLiteRepository(db_path=DB_PATH)
    await repo.init_db()
    
    # Test get user
    user = await repo.get_user(1)
    assert user is not None
    assert user.username == "alice"
    assert user.balance == 100.0
    
    # Test update user balance
    success = await repo.update_user_balance(1, 75.50)
    assert success is True
    user = await repo.get_user(1)
    assert user.balance == 75.50
    
    # Test get item
    item = await repo.get_item(101)
    assert item is not None
    assert item.stock == 5
    
    # Test update item stock
    success = await repo.update_item_stock(101, 3)
    assert success is True
    item = await repo.get_item(101)
    assert item.stock == 3


# ==============================================================================
# SECTION 2: TOKEN BUCKET RATE LIMITER TESTING
# ==============================================================================

@pytest.mark.asyncio
async def test_rate_limiter_limit():
    """Verify that requests exceeding capacity are blocked by the rate limiter."""
    # Capacity: 3 tokens, Refill rate: 0.1 tokens/sec (very slow refill)
    limiter = TokenBucketRateLimiter(capacity=3, refill_rate=0.1)
    
    # First 3 requests should be accepted
    assert await limiter.acquire("user_1") is True
    assert await limiter.acquire("user_1") is True
    assert await limiter.acquire("user_1") is True
    
    # 4th request should be rejected (bucket is empty)
    assert await limiter.acquire("user_1") is False


@pytest.mark.asyncio
async def test_rate_limiter_refill():
    """Verify that the bucket refills dynamically over time."""
    # Capacity: 1 token, Refill rate: 5 tokens/sec (very fast refill)
    limiter = TokenBucketRateLimiter(capacity=1, refill_rate=5.0)
    
    assert await limiter.acquire("user_2") is True
    assert await limiter.acquire("user_2") is False  # Empty now
    
    # Sleep 0.25 seconds -> bucket refills 1.25 tokens -> capped at 1.0 capacity
    await asyncio.sleep(0.25)
    
    assert await limiter.acquire("user_2") is True  # Success after refill
    assert await limiter.acquire("user_2") is False  # Empty again


@pytest.mark.asyncio
async def test_rate_limiter_isolation():
    """Verify rate limits are tracked independently for different client IDs."""
    limiter = TokenBucketRateLimiter(capacity=2, refill_rate=0.1)
    
    # User A consumes all tokens
    assert await limiter.acquire("alice") is True
    assert await limiter.acquire("alice") is True
    assert await limiter.acquire("alice") is False
    
    # User B should still be allowed (fully isolated)
    assert await limiter.acquire("bob") is True
    assert await limiter.acquire("bob") is True
    assert await limiter.acquire("bob") is False


@pytest.mark.asyncio
async def test_rate_limiter_capacity_cap():
    """Verify tokens do not accumulate past the configured capacity limit."""
    limiter = TokenBucketRateLimiter(capacity=2, refill_rate=10.0)
    
    # Wait to allow heavy refills
    await asyncio.sleep(0.1)
    
    # Acquire 2 tokens
    assert await limiter.acquire("user_3") is True
    assert await limiter.acquire("user_3") is True
    
    # 3rd acquire must fail if we strictly cap at 2 capacity
    assert await limiter.acquire("user_3") is False


# ==============================================================================
# SECTION 3: TRANSACTION & ROLLBACK TESTING
# ==============================================================================

@pytest.mark.asyncio
async def test_order_placement_success():
    """Verify successful transaction: reduces user balance, reduces stock, creates order."""
    repo = SQLiteRepository(db_path=DB_PATH)
    await repo.init_db()
    service = ECommerceService(repo)
    
    # Alice (100.0) buys 1 Coffee Maker (49.99)
    order = await service.place_order(user_id=1, item_id=101, quantity=1)
    
    assert order is not None
    assert order.id is not None
    assert order.total_price == 49.99
    
    # Verify balance is updated in DB
    user = await repo.get_user(1)
    assert user.balance == 50.01
    
    # Verify stock is updated in DB
    item = await repo.get_item(101)
    assert item.stock == 4
    
    # Verify order is recorded in DB
    orders = await repo.get_orders_by_user(1)
    assert len(orders) == 1
    assert orders[0].item_id == 101
    assert orders[0].quantity == 1


@pytest.mark.asyncio
async def test_order_placement_insufficient_balance():
    """Verify atomicity: if user balance is insufficient, no DB modifications occur (rollback)."""
    repo = SQLiteRepository(db_path=DB_PATH)
    await repo.init_db()
    service = ECommerceService(repo)
    
    # Bob has 20.0, tries to buy Coffee Maker (49.99)
    with pytest.raises(ValueError, match="Insufficient balance"):
        await service.place_order(user_id=2, item_id=101, quantity=1)
        
    # Verify Bob's balance remains exactly 20.0
    user = await repo.get_user(2)
    assert user.balance == 20.0
    
    # Verify Coffee Maker stock remains exactly 5
    item = await repo.get_item(101)
    assert item.stock == 5
    
    # Verify no order was written to database
    orders = await repo.get_orders_by_user(2)
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_order_placement_out_of_stock():
    """Verify atomicity: if item is out of stock, no DB changes occur (rollback)."""
    repo = SQLiteRepository(db_path=DB_PATH)
    await repo.init_db()
    service = ECommerceService(repo)
    
    # Alice has 100.0, tries to buy 6 Coffee Makers (only 5 in stock)
    with pytest.raises(ValueError, match="Out of stock"):
        await service.place_order(user_id=1, item_id=101, quantity=6)
        
    # Verify Alice's balance remains 100.0
    user = await repo.get_user(1)
    assert user.balance == 100.0
    
    # Verify stock remains 5
    item = await repo.get_item(101)
    assert item.stock == 5
    
    # Verify no order was written to database
    orders = await repo.get_orders_by_user(1)
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_order_placement_db_error_rollback():
    """Verify atomicity: if database write fails mid-transaction, all changes roll back."""
    repo = SQLiteRepository(db_path=DB_PATH)
    await repo.init_db()
    
    # Monkey-patch create_order to throw a database runtime exception
    original_create_order = repo.create_order
    
    async def failing_create_order(*args, **kwargs):
        raise sqlite3.OperationalError("Database disk image is malformed / Simulated write lock failure")
        
    repo.create_order = failing_create_order
    service = ECommerceService(repo)
    
    # Alice tries to buy Coffee Maker
    with pytest.raises((sqlite3.OperationalError, Exception)):
        await service.place_order(user_id=1, item_id=101, quantity=1)
        
    # CRITICAL: Since database write failed, user balance should NOT have been deducted, and stock should NOT be decremented!
    user = await repo.get_user(1)
    assert user.balance == 100.0, "Rollback failed! User balance was deducted despite database write error."
    
    item = await repo.get_item(101)
    assert item.stock == 5, "Rollback failed! Item stock was decremented despite database write error."
