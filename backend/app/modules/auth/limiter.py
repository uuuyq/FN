"""Bounded, process-local authentication throttling for single-worker deployment."""
import math
import time
from collections import OrderedDict, deque
from threading import Lock

from fastapi import HTTPException

from ...errors import error_detail


class AuthLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.buckets = OrderedDict()
        self.lock = Lock()

    def check(self, request, account):
        source = request.client.host if request.client else 'unknown'
        # Never trust caller-supplied forwarding headers as the source address.
        rules = [('global', 300), ('source:' + source, 30), ('account:' + account, 10)]
        with self.lock:
            now = self.clock()
            for key, limit in rules:
                bucket = self.buckets.setdefault(key, deque())
                while bucket and bucket[0] <= now - 60:
                    bucket.popleft()
                if len(bucket) >= limit:
                    retry = max(1, math.ceil(bucket[0] + 60 - now))
                    raise HTTPException(429, detail=error_detail('auth_rate_limited'),
                                        headers={'Retry-After': str(retry)})
            for key, _ in rules:
                self.buckets[key].append(now)
                self.buckets.move_to_end(key)
            while len(self.buckets) > 4096:
                self.buckets.popitem(last=False)
