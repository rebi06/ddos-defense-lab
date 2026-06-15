from collections import defaultdict, deque
from threading import Lock
from time import time
from dataclasses import dataclass

lock = Lock()

WINDOW_SECONDS = 10
MAX_REQUESTS_PER_WINDOW = 20
BLOCK_SECOND = 60

recent_requests_by_ip = defaultdict(deque)
blocked_until = {}
manually_blocked = set()

@dataclass
class BlockEvent:
    ip: str
    blocked_at: float
    reason: str

block_history: deque = deque(maxlen=200)
request_log: dict = {}  # ip → {"count": int, "last_seen": float}

rate_limiting_enabled = True
ip_blocking_enabled = True
emergency_mode = False

NORMAL_USER_IPS = {
    "10.142.33.21",
    "10.142.45.38",
    "10.142.51.102",
    "10.142.62.55",
    "10.142.78.3",
}


def check_request(client_ip: str, now: float | None = None):
    if now is None:
        now = time()

    with lock:
        if client_ip not in request_log:
            request_log[client_ip] = {"count": 0, "last_seen": 0}
        request_log[client_ip]["count"] += 1
        request_log[client_ip]["last_seen"] = now
        
        if emergency_mode:
            return False, "emergency_mode", 60

        if client_ip in manually_blocked:
            return False, "manually_blocked", 3600

        if client_ip in blocked_until:
            if blocked_until[client_ip] > now:
                retry_after = int(blocked_until[client_ip] - now)
                if ip_blocking_enabled:
                    return False, "blocked", retry_after
            else:
                del blocked_until[client_ip]

        if not rate_limiting_enabled:
            return True, None, None

        ip_queue = recent_requests_by_ip[client_ip]
        ip_queue.append(now)

        while ip_queue and now - ip_queue[0] > WINDOW_SECONDS:
            ip_queue.popleft()

        if len(ip_queue) > MAX_REQUESTS_PER_WINDOW:
            blocked_until[client_ip] = now + BLOCK_SECOND
            block_history.append(BlockEvent(
                ip=client_ip,
                blocked_at=now,
                reason="rate_limit",
            ))
            return False, "rate_limit", BLOCK_SECOND

        return True, None, None


def manual_block_ip(ip: str) -> bool:
    with lock:
        if ip in manually_blocked:
            return False
        manually_blocked.add(ip)
        block_history.append(BlockEvent(
            ip=ip,
            blocked_at=time(),
            reason="manual",
        ))
        return True


def manual_unblock_ip(ip: str) -> bool:
    with lock:
        if ip not in manually_blocked:
            return False
        manually_blocked.discard(ip)
        return True


def is_normal_user(ip: str) -> bool:
    return ip in NORMAL_USER_IPS


def set_rate_limiting(enabled: bool) -> None:
    global rate_limiting_enabled
    with lock:
        rate_limiting_enabled = enabled


def set_ip_blocking(enabled: bool) -> None:
    global ip_blocking_enabled
    with lock:
        ip_blocking_enabled = enabled


def set_emergency_mode(enabled: bool) -> None:
    global emergency_mode
    with lock:
        emergency_mode = enabled


def unblock_all() -> int:
    with lock:
        count = len(blocked_until)
        blocked_until.clear()
        manually_blocked.clear()
        block_history.clear()
        return count

def reset_request_log() -> None:
    with lock:
        request_log.clear()


def snapshot():
    with lock:
        return {
            "request_log": {
                ip: {
                    "count": info["count"],
                    "last_seen": info["last_seen"],
                    "is_normal_user": ip in NORMAL_USER_IPS,
                    "is_blocked": ip in blocked_until or ip in manually_blocked,
                }
                for ip, info in request_log.items()
            },
            "blocked_ips": list(blocked_until.keys()),
            "manually_blocked_ips": list(manually_blocked),
            "tracked_ips": len(recent_requests_by_ip),
            "recent_blocks": [
                {
                    "ip": e.ip,
                    "blocked_at": e.blocked_at,
                    "reason": e.reason,
                    "is_normal_user": e.ip in NORMAL_USER_IPS,
                }
                for e in list(block_history)[-20:]
            ],
            "total_blocks_recorded": len(block_history),
            "rate_limiting_enabled": rate_limiting_enabled,
            "ip_blocking_enabled": ip_blocking_enabled,
            "emergency_mode": emergency_mode,
        }