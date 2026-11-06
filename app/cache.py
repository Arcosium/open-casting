import threading
import time


class Cache:
    def __init__(self, url=None, namespace="oc"):
        self.namespace = namespace
        self.redis = None
        if url:
            import redis
            self.redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
        self.items = {}
        self.lock = threading.Lock()
        self.compute_lock = threading.Lock()

    def ping(self):
        return bool(self.redis.ping()) if self.redis else True

    def hit(self, key, limit, seconds):
        if self.redis:
            return bool(self.redis.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n<=tonumber(ARGV[2]) and 1 or 0", 1, self.namespace + ":limit:" + key, seconds, limit))
        with self.lock:
            now = time.monotonic()
            if len(self.items) > 10000:
                self.items = {k: v for k, v in self.items.items() if v[1] > now}
            count, end = self.items.get(key, (0, 0))
            if end <= now:
                count, end = 0, now + seconds
            self.items[key] = (count + 1, end)
            return count < limit

    def get(self, key):
        if self.redis:
            import json
            raw = self.redis.get(self.namespace + ":data:" + key)
            return json.loads(raw) if raw else None
        with self.lock:
            value, end = self.items.get("data:" + key, (None, 0))
            return value if end > time.monotonic() else None

    def set(self, key, value, seconds=2):
        if self.redis:
            import json
            self.redis.setex(self.namespace + ":data:" + key, seconds, json.dumps(value))
        else:
            with self.lock:
                self.items["data:" + key] = (value, time.monotonic() + seconds)

    def delete(self, key):
        if self.redis:
            self.redis.delete(self.namespace + ":data:" + key)
        else:
            with self.lock:
                self.items.pop("data:" + key, None)

    def remember(self, key, build, seconds=3):
        value = self.get(key)
        if value is not None:
            return value
        lock = self.redis.lock(self.namespace + ":build:" + key, timeout=30, blocking_timeout=30) if self.redis else self.compute_lock
        with lock:
            value = self.get(key)
            if value is None:
                value = build()
                self.set(key, value, seconds)
            return value
