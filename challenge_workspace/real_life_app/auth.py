import time
from typing import Optional, Dict
import asyncio

class AuthenticationService:
    def __init__(self):
        self._tokens = {
            "token_alice": "alice",
            "token_bob": "bob"
        }

    async def authenticate(self, token: str) -> Optional[str]:
        return self._tokens.get(token)

class TokenBucketRateLimiter:
    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: Dict[str, Dict[str, float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, client_id: str) -> bool:
        async with self._lock:
            now = time.time()
            if client_id not in self._buckets:
                self._buckets[client_id] = {"tokens": self.capacity, "last_refill": now}
            
            bucket = self._buckets[client_id]
            
            # Refill
            elapsed = now - bucket["last_refill"]
            refill_amount = elapsed * self.refill_rate
            bucket["tokens"] = min(self.capacity, bucket["tokens"] + refill_amount)
            bucket["last_refill"] = now
            
            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True
            return False