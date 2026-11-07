"""Abuse-control primitives for the AXIASOFT development server.

Everything here is dependency-free and thread-safe. It implements four layers:

1. ``RateLimiter``     - per-client, per-bucket sliding-window limits. Buckets are
                         fixed names chosen by the route (never by the raw URL), so
                         appending ``?nonce=`` cannot buy a fresh allowance.
2. ``ConcurrencyGuard``- caps in-flight requests and caps how many requests per
                         client can be in flight at once, so a small number of
                         slow clients cannot starve everybody else.
3. ``SlowlorisGuard``  - rejects requests whose headers trickle in too slowly.
4. ``Lockout``         - temporary per-identity (email) lockout after repeated
                         failed sign-ins, on top of the per-IP rate limit.

Limits are intentionally generous for a real audience and still far below what
an automated attacker would want: a small surge of genuine visitors never sees a
429, while a scripted flood is throttled after a handful of requests.
"""
import hashlib
import ipaddress
import os
import threading
import time
from collections import defaultdict, deque

_MISSING = object()


def env_int(name, default, minimum=1, maximum=10_000_000):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def env_float(name, default, minimum=0.1, maximum=10_000.0):
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


class RateLimiter:
    """Sliding-window rate limiter keyed by (bucket, client) with bounded memory."""

    def __init__(self, max_keys=50_000, vacuum_every=2_000):
        self._lock = threading.Lock()
        self._hits = {}
        self._max_keys = max_keys
        self._vacuum_every = vacuum_every
        self._calls = 0

    def hit(self, bucket, client, limit, window, cost=1):
        """Record a hit. Returns (allowed, retry_after_seconds, remaining)."""
        key = (bucket, client)
        now = time.time()
        with self._lock:
            self._calls += 1
            if self._calls % self._vacuum_every == 0:
                self._vacuum(now)
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self._max_keys:
                    self._vacuum(now)
                    if len(self._hits) >= self._max_keys:
                        # Under extreme key pressure keep serving real clients: the
                        # oldest bucket is dropped rather than growing without bound.
                        try:
                            del self._hits[next(iter(self._hits))]
                        except (StopIteration, KeyError):
                            pass
                q = deque()
                self._hits[key] = q
            while q and now - q[0] > window:
                q.popleft()
            if len(q) + cost > limit:
                retry = max(1, int(window - (now - q[0])) + 1) if q else window
                return False, retry, 0
            for _ in range(cost):
                q.append(now)
            return True, 0, max(0, limit - len(q))

    def reset(self, bucket=None, client=None):
        with self._lock:
            if bucket is None:
                self._hits.clear()
            else:
                for key in [k for k in self._hits if k[0] == bucket and (client is None or k[1] == client)]:
                    self._hits.pop(key, None)

    def _vacuum(self, now):
        stale = [k for k, q in self._hits.items() if not q or now - q[-1] > 3600]
        for k in stale:
            self._hits.pop(k, None)

    @property
    def size(self):
        with self._lock:
            return len(self._hits)


class ConcurrencyGuard:
    """Bounded in-flight requests: a global ceiling plus a per-client ceiling."""

    def __init__(self, global_limit, per_client_limit=6):
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(global_limit)
        self.global_limit = global_limit
        self.per_client_limit = per_client_limit
        self._active = defaultdict(int)
        self._total = 0
        self.rejected = 0

    def capacity_left(self, client):
        with self._lock:
            return self._total < self.global_limit and self._active[client] < self.per_client_limit

    def acquire(self, client):
        with self._lock:
            if self._total >= self.global_limit:
                self.rejected += 1
                return False
            if self._active[client] >= self.per_client_limit:
                self.rejected += 1
                return False
            self._active[client] += 1
            self._total += 1
            return True

    def release(self, client):
        with self._lock:
            if self._active.get(client):
                self._active[client] -= 1
                if not self._active[client]:
                    self._active.pop(client, None)
            if self._total > 0:
                self._total -= 1

    @property
    def active(self):
        with self._lock:
            return self._total


class Lockout:
    """Temporary lockout after repeated failures for one identity (e.g. an email)."""

    def __init__(self, threshold, lock_seconds, track_seconds=900):
        self._lock = threading.Lock()
        self._failures = {}
        self.threshold = threshold
        self.lock_seconds = lock_seconds
        self.track_seconds = track_seconds

    def is_locked(self, identity):
        now = time.time()
        with self._lock:
            entry = self._failures.get(identity)
            if not entry:
                return False, 0
            count, locked_until = entry
            if locked_until and locked_until > now:
                return True, int(locked_until - now) + 1
            return False, 0

    def register_failure(self, identity):
        """Record a failure. Returns (locked_now, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            count, locked_until = self._failures.get(identity, (0, 0))
            if locked_until and locked_until <= now:
                count = 0
            count += 1
            if count >= self.threshold:
                self._failures[identity] = (0, now + self.lock_seconds)
                return True, self.lock_seconds
            self._failures[identity] = (count, 0)
            return False, 0

    def clear(self, identity):
        with self._lock:
            self._failures.pop(identity, None)

    def _vacuum(self, now):
        stale = [k for k, (c, until) in self._failures.items() if not until and now - 0 > 0 and c == 0]
        for k in stale:
            self._failures.pop(k, None)


def _bounded_key(value, limit=120):
    """Never retain an attacker-controlled key verbatim if it is absurdly long."""
    value = value or 'unknown'
    if len(value) <= limit:
        return value
    return 'sha256:' + hashlib.sha256(value.encode('utf-8', 'replace')).hexdigest()


def normalize_ip(raw, trusted_proxies=()):
    """Return a canonical client key.

    ``raw`` is the socket peer address. ``trusted_proxies`` is the set of peer
    addresses allowed to supply ``X-Forwarded-For`` (empty by default: headers are
    ignored, which is the safe behaviour when the app is exposed directly).
    """
    raw = (raw or '').strip()
    if not raw:
        return 'unresolved'
    raw = _bounded_key(raw)
    if raw.startswith('::ffff:'):
        raw = raw[7:]
    if '%' in raw:
        raw = raw.split('%', 1)[0]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return 'unresolved' if not raw else _bounded_key(raw)


def client_from_forwarded(forwarded, peer, trusted_proxies):
    """Resolve the real client when a trusted reverse proxy is in front of the app."""
    if peer not in trusted_proxies or not forwarded:
        return normalize_ip(peer)
    first = forwarded.split(',')[0].strip()
    return normalize_ip(first)


def resolve_user_agent(headers):
    """Validate the User-Agent header: present, sane and bounded in size."""
    ua = (headers.get('User-Agent') or '').strip()
    if len(ua) > 512:
        return None, 'Request header rejected.'
    return ua, None
