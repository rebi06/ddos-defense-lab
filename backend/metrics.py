from collections import defaultdict, deque
from threading import Lock
from time import time 
import psutil

lock = Lock()

total_requests = 0 
endpoint_counts = defaultdict(int)
latencies = deque(maxlen=1000)
request_timestamps = deque()

TIMESTAMP_WINDOW = 60

def record_request(path: str) -> None:
    global total_requests
    now = time()
    with lock:
        total_requests += 1
        endpoint_counts[path] += 1
        request_timestamps.append(now)
        _cleanup_timestamps(now)
        
def _cleanup_timestamps(now: float) -> None:
    while request_timestamps and now - request_timestamps[0] > TIMESTAMP_WINDOW:
        request_timestamps.popleft()
        
def get_rps(window_sec: int = 10) -> float:
    now = time()
    with lock:
        count = sum(1 for ts in request_timestamps if now - ts <= window_sec)
        return round(count / window_sec, 2)
        
def record_latency(seconds: float) -> None:
    with lock:
        latencies.append(seconds)

def safe_avg(values) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

def snapshot() -> dict:
    with lock:
        latency_snapshot = list(latencies)
        endpoint_snapshot = dict(endpoint_counts)
        total_snapshot = total_requests

    return {
        "total_requests": total_snapshot,
        "endpoint_counts": endpoint_snapshot,
        "avg_latency_ms": round(safe_avg(latency_snapshot) * 1000, 1),
        "rps_10s": get_rps(10),
        "cpu_percent": round(psutil.cpu_percent(), 1),
        "memory_percent": round(psutil.virtual_memory().percent, 1),
    }